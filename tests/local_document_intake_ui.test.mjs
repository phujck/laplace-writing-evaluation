// Production intake controller consuming actual emitted owner standing, with DOM/transport doubles.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {openLocalDocumentIntake} from '../src/laplace/web/static_shared/local-document-intake.mjs';
import {createLocalDocumentDraft,retainIntakeSubmission} from '../src/laplace/web/static_shared/local-document-intake-port.mjs';
const samplePath=process.env.LOCAL_INTAKE_PARTIAL_SAMPLE,output=process.env.LOCAL_INTAKE_OUTPUT;
const sample=samplePath?JSON.parse(await readFile(samplePath,'utf8')):null;
const copy=value=>JSON.parse(JSON.stringify(value)),storage=()=>{const data=new Map();return {getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value)};};
test('retained original reload and explicit fresh link use no File or repeated raw upload',{skip:!sample},async()=>{
 const dom=installDOM(),oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(){};
 try{
  const partial=sample.retained||sample.partial,complete=sample.linked||sample.completed,project=partial.project,primary=storage(),backup=storage(),draft=createLocalDocumentDraft({project,storage:primary,backup}),intent=partial.intent,posts=[],uses=[];
  const pending=await retainIntakeSubmission(project,intent,{http:{method:'POST',url:'/projects/material-intake/upload'},query:{project},request_field:'request'},partial.read);
  draft.update({selection:{display_name:intent.display_name,media_type:intent.media_type,size:intent.declared_size,sha256:'sha256:'+intent.expected_sha256},pending,return_target:{session_id:'WS-original',context:{surface:'project',label:'Project'}}});
  const preparation={schema_version:'laplace.material-intake/1',project,metadata:{type:'object'},project_revision:'sha256:'+'d'.repeat(64),limits:{'application/pdf':16000000,'text/plain; charset=utf-8':2000000},actions:{upload:{permitted:true}}};
  let current=partial;const request=async(path,payload)=>{if(payload){posts.push({path,payload:copy(payload)});current=complete;return copy(complete);}const encoded=JSON.parse(new URL(path,'http://local').searchParams.get('request')||'{}');return copy(encoded.view==='describe'?preparation:current);};
  let dialog=await openLocalDocumentIntake({project,draft,request,returnTarget:{session_id:'WS-original',context:{surface:'project',label:'Project'}},upload:()=>{throw Error('No raw upload is allowed after retention.');},onUse:(...args)=>uses.push(args)});
  assert.match(dialog.textContent,/Original bytes retained/);assert.doesNotMatch(dialog.textContent,/Reselect the exact original/);assert.equal(findButton(dialog,'Retry same document'),undefined);assert.equal(posts.length,0);dialog.close();
  const reloaded=createLocalDocumentDraft({project,storage:primary,backup});dialog=await openLocalDocumentIntake({project,draft:reloaded,request,returnTarget:{session_id:'WS-original',context:{surface:'project',label:'Project'}},upload:()=>{throw Error('Reload needs no original File.');},onUse:(...args)=>uses.push(args)});assert.equal(reloaded.selectedFile(reloaded.snapshot().selection),null);assert.equal(posts.length,0);
  await findButton(dialog,'Check project before adding to Sources').click();await findButton(dialog,'Add saved original to Sources').click();assert.equal(posts.length,1);assert.deepEqual(posts[0].payload,{project,request_id:intent.request_id,expected_revision:preparation.project_revision});assert.equal(reloaded.snapshot().pending.wire,pending.wire);assert.equal(reloaded.snapshot().standing.original.artifact_id,complete.original.artifact_id);
  await findButton(dialog,'Use in conversation').click();assert.equal(uses.length,1);assert.deepEqual(uses[0],[complete.original.material_read,complete.original.display_name,{session_id:'WS-original',context:{surface:'project',label:'Project'}}]);
  if(output)await writeFile(output+'/retained-link-reload.json',JSON.stringify({sample:samplePath,posts,uses,original_wire_unchanged:reloaded.snapshot().pending.wire===pending.wire,raw_uploads:0,meaning:'Actual emitted owner rows; production controller with DOM/transport doubles, no HTTP effects'},null,2));
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});
test('late captured absence cannot erase an already received retained-original receipt',{skip:!sample},async()=>{
 const dom=installDOM(),oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(){};
 try{
  const complete=sample.linked||sample.completed,project=complete.project,draft=createLocalDocumentDraft({project,storage:storage(),backup:storage()}),metadata=complete.intent,pending=await retainIntakeSubmission(project,metadata,{http:{method:'POST',url:'/projects/material-intake/upload'}},complete.read);
  draft.update({pending,selection:{display_name:metadata.display_name,media_type:metadata.media_type,size:metadata.declared_size,sha256:'sha256:'+metadata.expected_sha256}});
  let release,first=true;const delayed=new Promise(resolve=>release=resolve),request=async()=>first?(first=false,await delayed):copy(complete);
  const earlier=openLocalDocumentIntake({project,draft,request});await new Promise(resolve=>setTimeout(resolve,0));
  const current=await openLocalDocumentIntake({project,draft,request});assert.equal(draft.snapshot().standing.original.artifact_id,complete.original.artifact_id);
  release({schema_version:'laplace.material-intake-result/1',project,request_id:metadata.request_id,state:'NONE'});await earlier;
  assert.equal(draft.snapshot().standing.original.artifact_id,complete.original.artifact_id);assert.equal(draft.snapshot().latest_check.state,'NONE');assert.equal(draft.snapshot().pending.observation,'RECORDED');current.close();
  if(output)await writeFile(output+'/late-absence-receipt.json',JSON.stringify({request_id:metadata.request_id,retained:draft.snapshot().standing.original.artifact_id,latest_check:draft.snapshot().latest_check,meaning:'Two production controller visits; late captured NONE preserves exact earlier effect, no owner or network effects'},null,2));
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});
