import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {installDOM,findButton} from './helpers/evidence_reader_harness.mjs';
import {openFeedbackReply,openFeedbackResponses} from '../src/laplace/web/static_shared/feedback-route.mjs';
const a=process.env.FEEDBACK_ROUTE_SAMPLES?JSON.parse(await readFile(process.env.FEEDBACK_ROUTE_SAMPLES,'utf8')).aggregate:null;
const out=process.env.FEEDBACK_FOCUS_OUTPUT;
test('late final-page response does not steal focus after user moves to Close',{skip:!a},async()=>{
 const dom=installDOM(),prior=globalThis.sessionStorage;globalThis.sessionStorage=undefined;
 try{
  const handle=a.edges[0].public_reply_read,target=handle.identity,basis='sha256:'+'b'.repeat(64),text='Public END';let release;
  const page=(offset,end)=>({...target,schema_version:'laplace.writing-message-part/1',state:'AVAILABLE',basis,offset,end,total_characters:text.length,total_utf8_bytes:Buffer.byteLength(text),content:text.slice(offset,end),page_read:h(offset),next_read:end<text.length?h(end):null,restart_read:h(0,false)});
  const h=(offset,pin=true)=>({identity:target,http:{method:'GET',url:'/authoring/session-turn?'+new URLSearchParams({project:target.project,session_id:target.session_id,id:target.turn_id,part:'reply',view:'message',offset:String(offset),...(pin?{expected_basis:basis}:{})})}});
  const request=async path=>Number(new URL(path,'http://local').searchParams.get('offset')||0)===0?page(0,4):new Promise(resolve=>release=()=>resolve(page(4,text.length)));
  const dialog=await openFeedbackReply({project:a.project,handle,request}),more=findButton(dialog,'Continue reading response'),close=findButton(dialog,'Close response');
  const reading=more.click();while(!release)await new Promise(resolve=>setTimeout(resolve,0));close.focus();release();await reading;
  const proof={focus_before_release:'Close response',focus_after_release:document.activeElement.textContent,complete:more.hidden,transport:'Declared page double over actual owner target/handle; no HTTP/provider'};
  if(out)await writeFile(out+'/reply-focus-proof.json',JSON.stringify(proof,null,2));assert.equal(document.activeElement,close);dialog.close();
 }finally{globalThis.sessionStorage=prior;dom.restore();}
});
test('late aggregate refresh does not steal focus after user moves to Close',{skip:!a},async()=>{
 const dom=installDOM();try{let count=0,release;
  const request=async()=>++count===1?a:new Promise(resolve=>release=()=>resolve(a));
  const dialog=await openFeedbackResponses({project:a.project,workId:a.work.id,origin:a.origin.origin_ref,read:a.read,request}),refresh=findButton(dialog,'Refresh review responses'),close=findButton(dialog,'Close review responses');
  const reading=refresh.click();while(!release)await new Promise(resolve=>setTimeout(resolve,0));close.focus();release();await reading;
  const proof={focus_before_release:'Close review responses',focus_after_release:document.activeElement.textContent,read_count:count,transport:'Actual retained owner aggregate; local delayed transport, no HTTP/provider'};
  if(out)await writeFile(out+'/aggregate-focus-proof.json',JSON.stringify(proof,null,2));assert.equal(document.activeElement,close);dialog.close();
 }finally{dom.restore();}
});

test('response hierarchy leads with comment/outcomes and keeps exact facts in closed settings',{skip:!a},async()=>{
 const dom=installDOM();try{const value=structuredClone(a);value.edges[1].public_reply_read=null;value.edges[1].event={state:'UNCONFIRMED',reason:'delivery attempts or deadline exhausted without admitted coordinates',acceptance:{status:'AWAITING_REVIEW',currentness:'UNKNOWN'}};const dialog=await openFeedbackResponses({project:value.project,workId:value.work.id,origin:value.origin.origin_ref,read:value.read,request:async()=>value});
 assert.equal(dialog.children[2].textContent,value.origin.correction.text);assert.match(dialog.children[3].textContent,/1 response received · 1 start unconfirmed/);const row=dialog.querySelector('article');assert.match(row.textContent,/Response received/);assert.match(row.textContent,/Awaiting a recorded verdict/);assert.doesNotMatch(row.textContent,/TERMINAL|Transport attempts|Recipient acknowledgement|not document-only|monetary/);const settings=dialog.querySelectorAll('details').find(node=>node.children[0].textContent==='Review settings');assert.ok(settings);assert.ok(!settings.open);assert.match(settings.textContent,/TERMINAL/);assert.match(settings.textContent,/deadline exhausted/);dialog.close();
 }finally{dom.restore();}
});
