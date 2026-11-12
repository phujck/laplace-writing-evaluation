import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {installDOM,findButton} from './helpers/evidence_reader_harness.mjs';
import {openFeedbackComment} from '../src/laplace/web/static_shared/feedback-route.mjs';
const vector=process.env.FEEDBACK_ORIGIN_VECTOR?JSON.parse(await readFile(process.env.FEEDBACK_ORIGIN_VECTOR,'utf8')):null;
const policy=process.env.FEEDBACK_POLICY_SAMPLES?JSON.parse(await readFile(process.env.FEEDBACK_POLICY_SAMPLES,'utf8')):null;
const memory=()=>{const values=new Map();return {getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)};};
// Actual owner descriptors are consumed through a labelled local transport double.
// This case checks browser composition only, not execution or a delivered review.
test('already authored automatic policy makes one composed Save without a second per-edge Send',{skip:!vector||!policy},async()=>{
 const dom=installDOM(),old={sessionStorage:globalThis.sessionStorage,localStorage:globalThis.localStorage};globalThis.sessionStorage=memory();globalThis.localStorage=memory();const posts=[];
 try{const request=async(path,payload)=>{
  if(payload)posts.push({path,payload:structuredClone(payload)});
  if(path==='/authoring/correction-prepare'){const query={...vector.prepared.reconcile.http.query};delete query.request_id;return {...vector.prepared,reconcile:{http:{...vector.prepared.reconcile.http,query},requires:['request_id']}};}
  if(path.startsWith('/work/state?'))return {project:'p',tasks:[policy.preview.work],read_cut:{revision:'public-list-cut'}};
  if(path.startsWith('/work/delivery?')){const asked=JSON.parse(new URL(path,'http://local').searchParams.get('request')),next=structuredClone(policy.preview);next.actions.compose.route_spec.request_id=asked.request_id;return next;}
  if(path==='/authoring/correction')return {...vector.saved,request_id:payload.request_id,correction:{...vector.saved.correction,text:payload.text.trim(),anchor:payload.anchor},source_basis:payload.source_basis,review_route_spec:payload.review_route,review_route:{effect:'UNKNOWN',reason:'This test does not execute the route.'}};
  throw Error(path);
 };
 const dialog=await openFeedbackComment({project:'p',selection:{anchor:vector.prepared.anchor,prepare:vector.prepare_body},request}),input=dialog.querySelector('textarea');input.value=vector.payload.text;input.oninput();const details=dialog.all().find(n=>n.tag==='details'&&n.children[0]?.textContent==='Reviewers and limits');details.open=true;await details.ontoggle();const choose=dialog.all().find(n=>n.tag==='select'&&n.attrs['aria-label']==='Existing review Work');choose.value=policy.preview.work.id;await choose.onchange();const save=findButton(dialog,'Save comment and request reviews');assert.ok(save);assert.equal(findButton(dialog,'Save and request reviews').hidden,true);await save.click();assert.equal(posts.filter(p=>p.path==='/authoring/correction').length,1);assert.equal(posts.filter(p=>p.path==='/work/delivery').length,0);const wire=posts.at(-1).payload;assert.equal(wire.review_route.policy_id,policy.preview.policy.id);assert.deepEqual(wire.source_basis,vector.payload.source_basis);assert.equal(wire.text,vector.payload.text);assert.match(dialog.textContent,/Review routing: UNKNOWN/);dialog.close();
 }finally{dom.restore();Object.assign(globalThis,old);}
});
test('empty owner preview retains authored recipients; only the route form waits during its read',{skip:!vector||!policy},async()=>{
 const {createFeedbackDraft}=await import('../src/laplace/web/static_shared/feedback-route-port.mjs');const dom=installDOM(),old={sessionStorage:globalThis.sessionStorage,localStorage:globalThis.localStorage};globalThis.sessionStorage=memory();globalThis.localStorage=memory();
 try{const held=createFeedbackDraft({project:'p',key:'passage-comment'});held.update({text:'Retained comment',selection:{anchor:vector.prepared.anchor,prepare:vector.prepare_body},prepared:vector.prepared,request_id:null,route_work:policy.preview.work.id,route_form:{mode:'manual',recipients:policy.preview.policy.recipients,limits:policy.preview.policy.limits}});let release;
 const request=async(path,payload)=>{if(path==='/authoring/correction-prepare'){const response=structuredClone(vector.prepared);delete response.reconcile.http.query.request_id;response.reconcile.requires=['request_id'];return response;}if(path.startsWith('/work/state?'))return new Promise(resolve=>release=()=>resolve({project:'p',tasks:[policy.preview.work],read_cut:{revision:'list'}}));if(path.startsWith('/work/delivery?')){const response=structuredClone(policy.preview);response.policy=null;response.selected_recipients=[];response.recipients=[];response.actions.compose.permitted=false;response.issues=['Manual Save-only until selected policy is previewed.'];return response;}throw Error(path);};
 const dialog=await openFeedbackComment({project:'p',selection:{anchor:vector.prepared.anchor,prepare:vector.prepare_body},request}),detail=dialog.all().find(n=>n.tag==='details'&&n.children[0]?.textContent==='Reviewers and limits');detail.open=true;const reading=detail.ontoggle();while(!release)await new Promise(resolve=>setTimeout(resolve,0));assert.equal(dialog.querySelector('fieldset').disabled,true);const prose=dialog.querySelector('textarea');prose.value='Later prose stays editable';prose.oninput();release();await reading;assert.equal(dialog.querySelector('fieldset').disabled,false);assert.equal(prose.value,'Later prose stays editable');assert.equal(dialog.all().filter(n=>n.tag==='input'&&n.type==='checkbox'&&n.checked).length,2);assert.equal(findButton(dialog,'Save and request reviews').disabled,true);dialog.close();
 }finally{dom.restore();Object.assign(globalThis,old);}
});
