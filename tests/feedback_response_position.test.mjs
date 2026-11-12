// Actual owner aggregate/handle, with local paged-message transport and DOM double.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {installDOM,findButton} from './helpers/evidence_reader_harness.mjs';
import {openFeedbackResponses} from '../src/laplace/web/static_shared/feedback-route.mjs';
import {sharedInspector} from '../src/laplace/web/static_shared/workspace-inspector.mjs';
const samples=process.env.FEEDBACK_ROUTE_SAMPLES?JSON.parse(await readFile(process.env.FEEDBACK_ROUTE_SAMPLES,'utf8')):null;
test('last response page retains focus; Back restores exact prior aggregate, row and read extent',{skip:!samples},async()=>{
 const dom=installDOM(),prior=globalThis.sessionStorage,storage=new Map();globalThis.sessionStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)};
 try{
  const a=samples.aggregate,target=a.edges[0].public_reply_read.identity,basis='sha256:'+'a'.repeat(64),text='Public Unicode αβ END',cut=10;let aggregateReads=0,messageReads=0;
  const handle=(offset=0,pin=true)=>({identity:target,http:{method:'GET',url:'/authoring/session-turn?'+new URLSearchParams({project:target.project,session_id:target.session_id,id:target.turn_id,part:'reply',view:'message',offset:String(offset),...(pin?{expected_basis:basis}:{})})}});
  const request=async path=>{const url=new URL(path,'http://local');if(url.pathname==='/work/delivery'){aggregateReads++;return a;}messageReads++;const offset=Number(url.searchParams.get('offset')||0),end=Math.min(offset+cut,text.length);return {...target,schema_version:'laplace.writing-message-part/1',state:'AVAILABLE',basis,offset,end,total_characters:text.length,total_utf8_bytes:Buffer.byteLength(text),content:text.slice(offset,end),page_read:handle(offset),next_read:end<text.length?handle(end):null,restart_read:handle(0,false)};};
  const aggregate=await openFeedbackResponses({project:a.project,workId:a.work.id,origin:a.origin.origin_ref,read:a.read,request});aggregate.scrollTop=120;await findButton(aggregate,'Read complete response').click();
  let reply=sharedInspector().current.dialog;while(!findButton(reply,'Continue reading response').hidden)await findButton(reply,'Continue reading response').click();assert.equal(reply.querySelector('.feedback-route-response').textContent,text);assert.equal(document.activeElement,reply.querySelector('.feedback-route-response'));
  await findButton(reply,'Back to Review responses').click();const previous=sharedInspector().current.dialog;assert.match(previous.textContent,/Previously inspected/);assert.equal(aggregateReads,1);assert.equal(previous.scrollTop,120);assert.equal(document.activeElement.textContent,'Read complete response');assert.equal(findButton(previous,'Recover outstanding reviews'),undefined);
  const before=messageReads;await findButton(previous,'Read complete response').click();reply=sharedInspector().current.dialog;assert.equal(reply.querySelector('.feedback-route-response').textContent,text);assert.equal(findButton(reply,'Continue reading response').hidden,true);assert.equal(messageReads-before,Math.ceil(text.length/cut));
  await findButton(reply,'Back to Review responses').click();const back=sharedInspector().current.dialog;await findButton(back,'Refresh review responses').click();assert.equal(aggregateReads,2);assert.equal(document.activeElement.textContent,'Refresh review responses');assert.equal(sharedInspector().current.dialog.scrollTop,120);sharedInspector().current.dialog.close();
 }finally{globalThis.sessionStorage=prior;dom.restore();}
});
