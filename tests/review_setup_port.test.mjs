import test from 'node:test';
import assert from 'node:assert/strict';
import {createReviewSetupDraft,retainSetupStep,setupStepPayload,ordinarySetupQuestion,setupProviderOptions,canonicalSetupQuestions,mergeSetupQuestions} from '../src/laplace/web/static_shared/review-setup-port.mjs';
import {providerEffortOptions,providerModelOptions} from '../src/laplace/web/static_shared/provider-options.mjs';
const memory=()=>{const rows=new Map();return {getItem:key=>rows.get(key)||null,setItem:(key,value)=>rows.set(key,value),rows};};
test('setup reload retains original guarded step, full specialised definition and newer typing',async()=>{
 const storage=memory(),backup=memory(),draft=createReviewSetupDraft({project:'p',workId:'w',storage,backup}),special={id:'closure',scope:'closure',label:'Keep closure',required:true,independent:true,inputs:[],closure_work_id:'child'};
 const payload={project:'p',id:'w',expected_work_revision:'old',review_obligations:[special]},step=await retainSetupStep('questions',payload,{http:{method:'POST',url:'/work/task'}},{project:'p',workId:'w'});draft.update({definitions:[special],pending:step});draft.update({definitions:[{...special,label:'New typing'}]});const restored=createReviewSetupDraft({project:'p',workId:'w',storage,backup}).snapshot();assert.deepEqual(await setupStepPayload(restored.pending),payload);assert.equal(restored.definitions[0].label,'New typing');assert.equal(ordinarySetupQuestion(special),false);
 const broken={...step,wire:step.wire.replace('old','new')};await assert.rejects(()=>setupStepPayload(broken),/damaged/);await assert.rejects(()=>retainSetupStep('bind',{project:'other',work_id:'w'},{},{project:'p',workId:'w'}),/another Work/);
});
test('selected setup falls back before refusing persistence; unreadable custody is not overwritten',()=>{
 const backup=memory(),broken={getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}},draft=createReviewSetupDraft({project:'p',workId:'w',storage:broken,backup});draft.update({label:'Retained'});assert.equal(draft.persist(),true);assert.equal(createReviewSetupDraft({project:'p',workId:'w',storage:broken,backup}).snapshot().label,'Retained');const key=[...backup.rows.keys()][0];backup.rows.set(key,'{damaged');const bad=createReviewSetupDraft({project:'p',workId:'w',storage:broken,backup});assert.equal(bad.unreadable,true);assert.equal(bad.persist(),false);assert.equal(backup.rows.get(key),'{damaged');
});
test('shared passive choices preserve conversation options without choosing a first setup model',()=>{
 const provider={id:'p',name:'Public',models:[{id:'m',name:'Model',efforts:['low','high']}]};assert.equal(providerModelOptions(provider),provider.models);assert.deepEqual(providerEffortOptions(provider.models[0]),['low','high']);assert.deepEqual(providerEffortOptions({supports_effort:false}),['medium']);const choices=setupProviderOptions([provider],{provider:'p'});assert.deepEqual(choices.models,[{value:'m',label:'Model'}]);assert.equal(Object.hasOwn(choices,'selectedModel'),false);assert.equal(ordinarySetupQuestion({scope:'source',source_contract:{operation:'x'}}),false);
});

test('comparison preserves specialised/current additions and keeps conflicting prose available',()=>{
 const ordinary={id:'question',scope:'other',label:'Old',required:true,independent:true,inputs:['paper.tex']},special={id:'closure',scope:'closure',label:' Keep exactly ',required:true,independent:true,inputs:[],closure_work_id:'child'},raw=[{...ordinary,label:' New α 🧪 ',inputs:['paper.tex','paper.tex']},special],normal=canonicalSetupQuestions(raw);assert.equal(normal[0].label,'New α 🧪');assert.deepEqual(normal[0].inputs,['paper.tex']);assert.deepEqual(normal[1],special);assert.equal(raw[0].label,' New α 🧪 ');
 const added={...ordinary,id:'added',label:'Other author question'},merged=mergeSetupQuestions([ordinary,special],[{...ordinary,label:'My new question'},special],[ordinary,special,added]);assert.equal(merged[0].label,'My new question');assert.deepEqual(merged[1],special);assert.deepEqual(merged[2],added);assert.throws(()=>mergeSetupQuestions([ordinary],raw.slice(0,1),[]),/Copy its prose/);assert.equal(raw[0].label,' New α 🧪 ');
});
