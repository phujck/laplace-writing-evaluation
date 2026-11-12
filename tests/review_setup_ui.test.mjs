// Real emitted owner preparations/receipts with a local DOM and transport double; no owner effect claim.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {installDOM,findButton} from './helpers/evidence_reader_harness.mjs';
import {openReviewSetup,renderSetupQuestions} from '../src/laplace/web/static_shared/review-setup.mjs';
const folder=process.env.REVIEW_SETUP_SAMPLES;
const sample=folder?JSON.parse(await readFile(folder+'/unmanaged-and-specialised.json','utf8')):null;
const renewal=process.env.REVIEW_SETUP_RENEWAL?JSON.parse(await readFile(process.env.REVIEW_SETUP_RENEWAL,'utf8')):null;
const copy=value=>JSON.parse(JSON.stringify(value));
const memory=()=>{const values=new Map();return {getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)};};
const input=(dialog,label)=>dialog.all().find(node=>node.attrs?.['aria-label']===label);
const catalogue={providers:[{id:'claude',models:[{id:'haiku',name:'Haiku',efforts:['low','medium','high']}]}]};
function fixture(){const dom=installDOM(),previous=[globalThis.sessionStorage,globalThis.localStorage];globalThis.sessionStorage=memory();globalThis.localStorage=memory();return ()=>{[globalThis.sessionStorage,globalThis.localStorage]=previous;dom.restore();};}
test('question Save keeps specialised fields and later typing; no approval starts a review',{skip:!sample},async()=>{
 const done=fixture();try{let current=copy(sample.complete),release,submitted,posts=0;const initial=copy(current);
 const request=async(path,payload)=>{if(path==='/authoring/providers')return catalogue;if(payload){assert.equal(path,'/work/task');posts++;submitted=copy(payload);return new Promise(resolve=>release=()=>{current={...copy(current),review_obligations:copy(payload.review_obligations)};resolve({...sample.saved_result,work_revision:current.work.revision});});}return copy(current);};
 const dialog=await openReviewSetup({project:current.project,workId:current.work.id,request});const editable=initial.review_obligations.findIndex(row=>!row.closure_work_id&&!row.source_contract&&row.scope!=='closure'),field='Question '+(editable+1);input(dialog,field).value='Submitted question';input(dialog,field).oninput();const writing=findButton(dialog,'Save review setup').click();while(!release)await new Promise(resolve=>setTimeout(resolve,0));input(dialog,field).value='Later question typing';input(dialog,field).oninput();release();await writing;
 assert.equal(posts,1);assert.equal(input(dialog,field).value,'Later question typing');for(const row of initial.review_obligations.filter(row=>row.closure_work_id||row.source_contract))assert.deepEqual(submitted.review_obligations.find(value=>value.id===row.id),row);assert.match(dialog.textContent,/later question edits remain unsaved/);dialog.close();
 }finally{done();}
});
test('unknown question Save stops before approvals and needs explicit matching-standing adoption',{skip:!sample},async()=>{
 const done=fixture();try{let current=copy(sample.complete),posts=0;const request=async(path,payload)=>{if(path==='/authoring/providers')return catalogue;if(payload){posts++;current.review_obligations=copy(payload.review_obligations);throw Error('Lost question response');}return copy(current);};const dialog=await openReviewSetup({project:current.project,workId:current.work.id,request}),at=current.review_obligations.findIndex(row=>!row.closure_work_id&&!row.source_contract&&row.scope!=='closure'),label='Question '+(at+1);input(dialog,label).value='Unknown saved question';input(dialog,label).oninput();await findButton(dialog,'Save review setup').click();assert.equal(posts,1);assert.equal(findButton(dialog,'Save review setup').disabled,true);await findButton(dialog,'Check setup save').click();assert.ok(findButton(dialog,'Use inspected matching questions'));assert.equal(posts,1);await findButton(dialog,'Use inspected matching questions').click();assert.match(dialog.textContent,/Review questions match the intended setup/);assert.equal(findButton(dialog,'Save review setup').disabled,false);dialog.close();
 }finally{done();}
});
test('expired renewal retains exact wire after loss then pure lookup settles one receipt',{skip:!renewal},async()=>{
 const done=fixture();try{let current=copy(renewal.expired_setup),posts=0,wire;const request=async(path,payload)=>{if(path==='/authoring/providers')return catalogue;if(payload){posts++;wire=copy(payload);current=copy(renewal.current_setup);throw Error('Lost renewal response');}const q=JSON.parse(new URL(path,'http://local').searchParams.get('request'));if(q.action==='renew-request')return {effect:'RECORDED',receipt:{...renewal.renewed,request_id:wire.request_id,previous_revision:wire.expected_binding_revision}};return copy(current);};
 const dialog=await openReviewSetup({project:current.project,workId:current.work.id,request});await findButton(dialog,/Include renewal for/).click();await findButton(dialog,'Save review setup').click();assert.equal(posts,1);assert.equal(wire.recipient_binding_id,renewal.wire.recipient_binding_id);assert.equal(wire.expected_binding_revision,renewal.wire.expected_binding_revision);await findButton(dialog,'Check setup save').click();assert.equal(posts,1);assert.match(dialog.textContent,/Approval renewed/);dialog.close();
 }finally{done();}
});

test('late Save after close leaves the reopened draft typing intact',{skip:!sample},async()=>{
 const done=fixture();try{let current=copy(sample.complete),release;const request=async(path,payload)=>{if(path==='/authoring/providers')return catalogue;if(payload)return new Promise(resolve=>release=()=>{current.review_obligations=copy(payload.review_obligations);resolve({...sample.saved_result,work_revision:current.work.revision});});return copy(current);};
 const first=await openReviewSetup({project:current.project,workId:current.work.id,request}),at=current.review_obligations.findIndex(row=>!row.closure_work_id&&!row.source_contract&&row.scope!=='closure'),label='Question '+(at+1);input(first,label).value='First submitted question';input(first,label).oninput();const pending=findButton(first,'Save review setup').click();while(!release)await new Promise(resolve=>setTimeout(resolve,0));first.close();const second=await openReviewSetup({project:current.project,workId:current.work.id,request});input(second,label).value='Typing in reopened setup';input(second,label).oninput();release();await pending;assert.equal(input(second,label).value,'Typing in reopened setup');await findButton(second,'Check setup save').click();await findButton(second,'Use inspected matching questions').click();assert.equal(input(second,label).value,'Typing in reopened setup');second.close();
 }finally{done();}
});
test('binding pages retain one cut and refuse a changed page without dropping inspected approvals',{skip:!folder},async()=>{
 const done=fixture();try{const rows=JSON.parse(await readFile(folder+'/binding-pages.json','utf8'));let page=0,changed=false;const request=async path=>{if(path==='/authoring/providers')return catalogue;if(changed){const value=copy(rows.pages[0]);value.bindings.cut='sha256:'+'f'.repeat(64);return value;}return copy(page++?rows.pages[0]:rows.first);};const dialog=await openReviewSetup({project:rows.first.project,workId:rows.first.work.id,request});const before=dialog.textContent;changed=true;await findButton(dialog,'More reviewers').click();assert.match(dialog.textContent,/changed between pages/);assert.ok(dialog.textContent.includes(rows.first.bindings.items[0].binding.label));assert.equal(dialog.all().filter(node=>node.tag==='h4').length,rows.first.bindings.items.length);dialog.close();
 }finally{done();}
});

test('More reviewers reaches all20 unique latest identities through issued same-cut handles',{skip:!folder},async()=>{
 const done=fixture();try{const rows=JSON.parse(await readFile(folder+'/binding-pages.json','utf8'));const request=async path=>{if(path==='/authoring/providers')return catalogue;const payload=JSON.parse(new URL(path,'http://local').searchParams.get('request'));return copy(rows.pages.find(row=>row.bindings.offset===(payload.offset||0)));};const dialog=await openReviewSetup({project:rows.first.project,workId:rows.first.work.id,request});while(findButton(dialog,'More reviewers'))await findButton(dialog,'More reviewers').click();assert.equal(dialog.all().filter(node=>node.tag==='h4').length,20);assert.match(dialog.textContent,/20 of 20 reviewer approvals inspected/);dialog.close();
 }finally{done();}
});

test('question metadata is optional and retains explicit open/close state through text edits',{skip:!sample},()=>{
 const done=fixture();try{const host=document.createElement('section');document.body.append(host);let definitions=[copy(sample.complete.review_obligations.find(row=>!row.closure_work_id&&!row.source_contract&&row.scope!=='closure'))],opened={};const defaults={required:true,independent:true};const paint=()=>renderSetupQuestions(host,{definitions,scopes:sample.complete.question_contract.scopes.filter(value=>value!=='closure'),defaults,settingsOpen:opened,onSettingsChange:(id,value)=>{opened={...opened,[id]:value};},onChange:value=>{definitions=value;paint();}});paint();let settings=host.querySelector('details');assert.equal(settings.open,false);assert.match(host.children[1].textContent,/Optional · independent review · 1 source input/);assert.equal(input(host,'Question 1').parentElement.parentElement.tag,'fieldset');assert.ok(settings.all().includes(input(host,'Review scope 1')));settings.open=true;settings.ontoggle();input(host,'Question 1').value='Later question text';input(host,'Question 1').oninput();settings=host.querySelector('details');assert.equal(settings.open,true);settings.open=false;settings.ontoggle();paint();assert.equal(host.querySelector('details').open,false);assert.equal(definitions[0].label,'Later question text');
 }finally{done();}
});
