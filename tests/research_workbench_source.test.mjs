import test from 'node:test';
import assert from 'node:assert/strict';
import {installHTMLDocument} from './helpers/html_dom.mjs';
import {openResearchSourceWindow} from '../src/laplace/web/static_shared/research-workbench-readers.mjs';
const pin='sha256:'+'a'.repeat(64),reference={schema_version:'laplace.reference/1',owner:'domain.projects',kind:'source-file',identity:{project:'public',path:'paper.tex',scope:'manuscript'}};
const handle=offset=>({http:{method:'GET',url:'/work/discovery?'+new URLSearchParams({facet:'object',reference:JSON.stringify(reference),section:'body',as_of:pin,offset:String(offset),limit:'4'})}});
function page(offset,content,total,next=null){return {schema_version:'laplace.object-facets/1',view:'object',subject:reference,basis:pin,scope_id:'public-scope',scope:{kind:'owned-workspace'},coverage:{},facets:{purpose:{value:{title:'Public manuscript'}}},items:[{offset,end:offset+Array.from(content).length,total_characters:total,content}],pagination:{next_read:next}};}

test('Pinned manuscript windows preserve exact Unicode extent and follow only the offered continuation',async()=>{
 const dom=installHTMLDocument(),calls=[];
 try{
  const dialog=await openResearchSourceWindow({handle:handle(0),scopeId:'public-scope',request:async url=>{calls.push(url);return calls.length===1?page(0,'α 中🌱',8,handle(4)):page(4,' END',8);}});
  assert.match(dialog.textContent,/Characters 0–4 of 8/);assert.match(dialog.textContent,/α 中🌱/);
  await dialog.querySelectorAll('button').find(n=>n.textContent==='Read next source window').onclick();
  assert.equal(calls.length,2);assert.match(calls[1],/offset=4/);assert.match(dialog.textContent,/Characters 4–8 of 8/);assert.match(dialog.textContent,/ END/);assert.ok(!dialog.textContent.includes('complete source in this reading'));
  dialog.close();
 }finally{dom.restore();}
});

test('Source-window admission refuses arbitrary reads, and late foreign-scope replies cannot repaint a closed inspector',async()=>{
 const dom=installHTMLDocument();let reads=0,resolve,current=true;
 try{
  await assert.rejects(openResearchSourceWindow({handle:{http:{method:'GET',url:'/projection/tex?corpus=public&file=paper.tex'}},scopeId:'public-scope',request:async()=>{reads++;}}),/issued source reference/);assert.equal(reads,0);
  let began;const entered=new Promise(done=>{began=done;});const pending=openResearchSourceWindow({handle:handle(0),scopeId:'public-scope',isCurrent:()=>current,request:()=>{began();return new Promise(done=>{resolve=done;});}});
  await entered;const dialog=document.querySelector('dialog');current=false;dialog.close();resolve({...page(0,'OLD',3),scope_id:'foreign'});await pending;
  assert.equal(document.querySelector('dialog'),null);
 }finally{dom.restore();}
});
