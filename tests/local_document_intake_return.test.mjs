// Focused reading/return correction; actual issued page rows, no HTTP/upload/provider.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {findButton} from './helpers/evidence_reader_harness.mjs';
import {installInspectorCloseDOM} from './helpers/inspector_close_harness.mjs';
import {openLocalDocumentIntake} from '../src/laplace/web/static_shared/local-document-intake.mjs';
import {createLocalDocumentDraft,retainIntakeSubmission,focusIntakeDestination} from '../src/laplace/web/static_shared/local-document-intake-port.mjs';
import {WorkspaceSession} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {sharedInspector} from '../src/laplace/web/static_shared/workspace-inspector.mjs';
const samplePath=process.env.LOCAL_INTAKE_READING_SAMPLE,output=process.env.LOCAL_INTAKE_OUTPUT,sample=samplePath?JSON.parse(await readFile(samplePath,'utf8')):null;
const cp=x=>JSON.parse(JSON.stringify(x)),storage=()=>{const rows=new Map();return {getItem:k=>rows.get(k)||null,setItem:(k,v)=>rows.set(k,v)};};
async function fixture(){const saved=sample.saved,project=saved.project,draft=createLocalDocumentDraft({project,storage:storage(),backup:storage()}),pending=await retainIntakeSubmission(project,saved.intent,{http:{method:'POST',url:'/projects/material-intake/upload'}},saved.read);draft.update({pending,selection:{display_name:saved.intent.display_name,media_type:saved.intent.media_type,size:saved.intent.declared_size,sha256:'sha256:'+saved.intent.expected_sha256}});return {saved,project,draft,request:async path=>{const p=JSON.parse(new URL(path,'http://local').searchParams.get('request'));return cp(p.view==='status'?saved:sample.pages.find(v=>v.offset===(p.offset||0)));}};}
test('inspected page extent survives actual inspector Back and returns to composer',{skip:!sample},async()=>{
 const dom=installInspectorCloseDOM();
 try{const f=await fixture(),uses=[],composer=document.createElement('textarea');composer.value='HELD DRAFT α 中 🌱';document.body.append(composer);
  let dialog=await openLocalDocumentIntake({...f,onUse:p=>{uses.push(cp(p));return {element:composer};}});
  await findButton(dialog,'Inspect document text').click();await findButton(dialog,'Read more source').click();
  const pane=dialog.children.at(-1);assert.equal(pane.children[0].textContent,f.saved.original.display_name);assert.match(pane.children[1].textContent,/Text · bytes/);assert.equal(pane.children[2].tag,'details');assert.notEqual(pane.children[2].open,true);assert.doesNotMatch(pane.textContent,/Consumed: Not linked/);assert.equal(pane.children[3].textContent,sample.pages[1].content);
  const retained=f.draft.snapshot().reading;assert.deepEqual(retained.pointer,sample.pages[1].material_read);assert.deepEqual(retained.handle,sample.pages[1].page_read);assert.equal(JSON.stringify(retained).includes(sample.pages[1].content),false);
  const child=document.createElement('dialog');document.body.append(child);sharedInspector().adopt(child,{kind:'owner-read',title:'Nested reading',reopen:{factory:()=>{},args:{}}});child.showModal();await sharedInspector().back();dialog=document.body.children.filter(n=>n.tag==='dialog').at(-1);
  assert.match(dialog.children.at(-1).textContent,/Last inspected/);assert.ok(findButton(dialog,'Reinspect selected reading'));await findButton(dialog,'Use in conversation').click();await new Promise(setImmediate);assert.deepEqual(uses,[sample.pages[1].material_read]);assert.equal(document.activeElement,composer);assert.equal(composer.value,'HELD DRAFT α 中 🌱');
  if(output)await writeFile(output+'/reading-back-focus.json',JSON.stringify({sample:samplePath,retained,used:uses[0],composer_unchanged:composer.value,primary_coverage:retained.coverage.label,metadata_default_closed:true,meaning:'Production intake + actual sharedInspector Back; owner rows with DOM/transport doubles, no uploads/HTTP'},null,2));
 }finally{dom.restore();}
});
test('explicit Material action closes intake and focuses its returned destination',{skip:!sample},async()=>{
 const dom=installInspectorCloseDOM();
 try{const f=await fixture(),heading=document.createElement('h2');heading.textContent='Material';document.body.append(heading);const dialog=await openLocalDocumentIntake({...f,onMaterial:async()=>({element:heading,isCurrent:()=>true})});await findButton(dialog,'View in Sources').click();await new Promise(setImmediate);assert.equal(dialog.open,false);assert.equal(document.activeElement,heading);
  if(output)await writeFile(output+'/material-destination-focus.json',JSON.stringify({closed:true,focused:heading.textContent,meaning:'Production action-close destination; local DOM, no owner or navigation effects'},null,2));
 }finally{dom.restore();}
});
test('late destination completion respects later focus and navigation',async()=>{
 const listeners=new Map(),initial={},later={},body={},calls=[];const page={activeElement:initial,body,addEventListener:(n,fn)=>listeners.set(n,fn),removeEventListener:(n,fn)=>{assert.equal(listeners.get(n),fn);listeners.delete(n);}};
 let release;const delayed=new Promise(resolve=>release=resolve),pending=focusIntakeDestination(()=>delayed,{page});page.activeElement=later;listeners.get('focusin')({type:'focusin',target:later});release({element:{isConnected:true,focus:()=>calls.push('stolen')}});await pending;assert.deepEqual(calls,[]);assert.equal(listeners.size,0);
 await focusIntakeDestination(async()=>({element:{isConnected:true,focus:()=>calls.push('navigation stolen')},isCurrent:()=>false}),{page});assert.deepEqual(calls,[]);await focusIntakeDestination(async()=>({element:{isConnected:true,focus:()=>calls.push('current')}}),{page});assert.deepEqual(calls,['current']);assert.equal(listeners.size,0);
 if(output)await writeFile(output+'/destination-lifetime.json',JSON.stringify({calls,late_focus_preserved:true,changed_visit_preserved:true,listeners_after:0,meaning:'Focused destination service with event/DOM doubles, no app interaction'},null,2));
});

test('fresh retained-reading open captures current target while Back and later changes keep exact guards',{skip:!sample},async()=>{
 const proof=[];for(const change of [null,'target','session','epoch','intent']){const dom=installInspectorCloseDOM();try{const f=await fixture(),composer=document.createElement('textarea');composer.value='EXACT CURRENT DRAFT é中🌱';document.body.append(composer);const origin={session_id:'WS-upload-origin',context:{surface:'project',label:'Original upload'}};f.draft.update({return_target:origin});const originalWire=f.draft.snapshot().pending.wire;
 const session=Object.create(WorkspaceSession.prototype);Object.assign(session,{project:f.project,session:'WS-current',viewEpoch:7,intentRevision:12,messageIntent:{context:{surface:'sources',label:'Previously selected PDF',material_read:cp(sample.pages[0].material_read)}},selectionOverride:null,find:()=>composer,persistComposerDraft:()=>true,scope(){},status(){}});
 const opened=session.localDocumentTarget(),passed=[];let dialog=await openLocalDocumentIntake({...f,returnTarget:opened,onUse:(read,label,target)=>{passed.push(cp(target));session.useLocalDocument(read,label,target,{epoch:7,intentRevision:12});return {element:composer};}});
 // Deliberately mutate the caller's object: the open action and Back must keep their copy.
 opened.context.label='Changed outside';const child=document.createElement('dialog');document.body.append(child);sharedInspector().adopt(child,{title:'Nested source'});child.showModal();await sharedInspector().back();dialog=document.body.children.filter(n=>n.tag==='dialog').at(-1);
 if(change==='target')session.messageIntent.context.label='Later target';if(change==='session')session.session='WS-later';if(change==='epoch')session.viewEpoch++;if(change==='intent')session.intentRevision++;const before=cp(session.messageIntent);await findButton(dialog,'Use in conversation').click();await new Promise(setImmediate);
 assert.equal(passed[0].context.label,'Previously selected PDF');assert.equal(passed[0].session_id,'WS-current');assert.deepEqual(f.draft.snapshot().return_target,origin);assert.equal(f.draft.snapshot().pending.wire,originalWire);assert.equal(composer.value,'EXACT CURRENT DRAFT é中🌱');
 if(change){assert.equal(dialog.open,true);assert.deepEqual(session.messageIntent,before);assert.match(dialog.textContent,/original conversation or message target changed/);dialog.close();}else{assert.equal(dialog.open,false);assert.equal(document.activeElement,composer);assert.deepEqual(session.messageIntent.context.material_read,sample.pages[0].material_read);}
 proof.push({change:change||'none',used:!change,immutable_origin:origin,opened_target:passed[0],draft_unchanged:true,wire_unchanged:true});
 }finally{dom.restore();}}
 if(output)await writeFile(output+'/fresh-open-reading-target.json',JSON.stringify({proof,meaning:'Production intake, shared inspector Back and WorkspaceSession guarded action; actual emitted owner rows with local DOM/transport, no HTTP/upload/provider'},null,2));
});
