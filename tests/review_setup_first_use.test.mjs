import {test} from 'node:test';
import assert from 'node:assert/strict';
import {installDOM,Node} from './helpers/evidence_reader_harness.mjs';
import {renderSetupQuestions,approvalDurationControl} from '../src/laplace/web/static_shared/review-setup.mjs';
test('required question and review scope are visible together; ordinary edits preserve specialised fields',()=>{
 const dom=installDOM();try{const host=new Node('section');dom.body.append(host);let changed;
 const original={id:'q',label:'Explain Ω evidence',scope:'',required:true,independent:false,inputs:[]};renderSetupQuestions(host,{definitions:[original],scopes:['source','other'],defaults:{required:true,independent:true},onChange:rows=>changed=rows});
 const card=host.querySelector('fieldset'),scope=card.querySelector('select'),settings=card.querySelector('details');assert.equal(scope.required,true);assert.equal(scope.parentElement.parentElement,card,'scope is outside the optional settings disclosure');assert.ok(card.textContent.includes('Review scope (required)'));assert.ok(!settings.open);scope.value='source';scope.onchange();assert.equal(changed[0].scope,'source');assert.equal(changed[0].independent,false);assert.equal(original.scope,'');
 }finally{dom.restore();}
});
test('custom approval seconds are visible only for Custom and preserve exact numeric values',()=>{
 const dom=installDOM();try{let value;const control=approvalDurationControl({label:'Duration',value:3600,constraints:{minimum:1,maximum:999999},onChange:n=>value=n}).element;const choice=control.querySelector('select'),custom=control.querySelector('input');assert.equal(custom.parentElement.hidden,true);choice.value='custom';choice.onchange();assert.equal(custom.parentElement.hidden,false);custom.value='4817';custom.oninput();assert.equal(value,4817);choice.value='86400';choice.onchange();assert.equal(custom.parentElement.hidden,true);assert.equal(value,86400);
 }finally{dom.restore();}
});
