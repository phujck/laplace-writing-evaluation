import test from 'node:test';
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {createInspector} from '../src/laplace/web/static_shared/workspace-inspector.mjs';
import {installInspectorCloseDOM} from './helpers/inspector_close_harness.mjs';
const output=process.env.LOCAL_INTAKE_OUTPUT;
test('explicit close settles one owner and destination under either close-handler order',async()=>{
 const proof=[];for(const listenerFirst of [false,true]){const dom=installInspectorCloseDOM({listenerFirst});try{const service=createInspector(),opener=document.createElement('button'),destination=document.createElement('textarea'),dialog=document.createElement('dialog');document.body.append(opener,destination,dialog);opener.focus();let cleanup=0,handed=0;dialog.onclose=()=>{cleanup++;dialog.remove();};const token=service.adopt(dialog,{title:'Document'}).token;dialog.showModal();assert.equal(service.closeTo(token,()=>{assert.equal(service.current,null);assert.equal(service.trail.length,0);handed++;destination.focus();}),true);assert.equal(service.closeTo(token,()=>{throw Error('Second handoff');}),false);await dom.flushClose();assert.equal(document.activeElement,destination);assert.equal(cleanup,1);assert.equal(handed,1);proof.push({listenerFirst,cleanup,handed,final_focus:'destination'});}finally{dom.restore();}}
 if(output)await writeFile(output+'/single-close-owner.json',JSON.stringify({proof,meaning:'Production inspector; eventful DOM including native opener focus, two handler orders. Real browser test separate.'},null,2));
});
test('default Close and Back restore their existing opener and trail',async()=>{
 const dom=installInspectorCloseDOM();try{const service=createInspector(),opener=document.createElement('button');document.body.append(opener);opener.focus();let root,rootToken;const open=()=>{root=document.createElement('dialog');root.onclose=()=>root.remove();document.body.append(root);rootToken=service.adopt(root,{title:'Parent',reopen:open}).token;root.showModal();return root;};open();root.close();await dom.flushClose();assert.equal(document.activeElement,opener);assert.equal(service.current,null);open();const child=document.createElement('dialog');child.onclose=()=>child.remove();document.body.append(child);service.adopt(child,{title:'Child'});child.showModal();assert.equal(service.trail.length,1);await service.back();assert.equal(service.current.token,rootToken);assert.equal(service.trail.length,0);root.close();await dom.flushClose();assert.equal(service.current,null);assert.equal(document.activeElement,opener);
 if(output)await writeFile(output+'/default-close-back.json',JSON.stringify({default_close:'opener',back:'reopened parent',final_close:'opener',meaning:'Production default transitions; eventful local DOM'},null,2));
 }finally{dom.restore();}
});
test('replacement cancels an armed delayed destination and stale tokens cannot close the new visit',async()=>{
 const dom=installInspectorCloseDOM({deferClose:true});try{const service=createInspector(),first=document.createElement('dialog');document.body.append(first);const token=service.adopt(first,{title:'First'}).token;first.showModal();let handed=0;assert.equal(service.closeTo(token,()=>handed++),true);const next=document.createElement('dialog');document.body.append(next);const current=service.adopt(next,{title:'Later visit'}).token;next.showModal();await dom.flushClose();assert.equal(handed,0);assert.equal(service.current.token,current);assert.equal(next.open,true);assert.equal(service.closeTo(token,()=>handed++),false);next.close();await dom.flushClose();
 if(output)await writeFile(output+'/replacement-cancels-close.json',JSON.stringify({handed,stale_token_refused:true,later_visit_retained:true,meaning:'Production close owner with deliberately delayed close event'},null,2));
 }finally{dom.restore();}
});

test('later author focus before the close event cancels the destination without opener restoration',async()=>{
 const dom=installInspectorCloseDOM({deferClose:true});try{const service=createInspector(),opener=document.createElement('button'),later=document.createElement('button'),dialog=document.createElement('dialog');document.body.append(opener,later,dialog);opener.focus();const token=service.adopt(dialog,{title:'Document'}).token;dialog.showModal();let handed=0;service.closeTo(token,()=>handed++);later.focus();await dom.flushClose();assert.equal(handed,0);assert.equal(document.activeElement,later);assert.equal(service.current,null);
 if(output)await writeFile(output+'/later-author-close.json',JSON.stringify({handed,later_focus_preserved:true,meaning:'Author focus after native close restoration but before queued close event'},null,2));
 }finally{dom.restore();}
});
