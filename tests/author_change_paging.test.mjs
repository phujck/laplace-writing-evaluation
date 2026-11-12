import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {walkSource} from './helpers/walk_source.mjs';
const source=walkSource();
const start=source.indexOf('async function refreshAuthorChanges('),code=source.slice(start,source.indexOf('\nfunction setAuthorChanges(',start));
const node=()=>({children:[],append(...rows){this.children.push(...rows);}});
function fixture(){
 const calls=[],events=[];let clearCount=0,rejectCut=false;
 const context={URLSearchParams,authorChangesEnabled:true,authorChangesGeneration:0,authorChangesSuspended:false,authorHistoryPages:new Map(),authorChangeRecords:new Map(),S:{corpus:'p',blocks:[{src:{file:'chapter.tex'}}]},srcOf:b=>b.src,
 store:{fetchJSON:async path=>{calls.push(path);const u=new URL(path,'http://fixture');if(u.pathname==='/authoring/history'){
  if(rejectCut&&u.searchParams.has('as_of'))throw Object.assign(Error('History changed'),{status:409,refused:{status:'CHANGED_INPUT'}});
  const later=u.searchParams.get('offset')==='25';return{items:[{id:later?'AC-older':'AC-latest'}],as_of:'cut-exact',next_offset:later?null:25};
 }if(u.searchParams.has('id'))return{file:'chapter.tex',hunks:[{anchor:{file:'chapter.tex',line_start:1,line_end:1}}]};return{file:'chapter.tex',whole_file:true};}},
 captureFocus:()=>({}),clearAuthorChanges:()=>clearCount++,paintAuthorHunks:()=>1,syncRevisionHighlights(){},measure(){},restoreFocus(){},emit:(...args)=>events.push(args),docEl:{querySelector:()=>null,querySelectorAll:()=>[],append(){}},authorChangeNode:node,el:node};
 vm.createContext(context);vm.runInContext(code+';this.read=refreshAuthorChanges;',context);
 return{context,calls,events,clears:()=>clearCount,reject:()=>rejectCut=true};
}
test('walk fallback uses bounded same-owner history, continuation cut and exact correction details',async()=>{
 const f=fixture();await f.context.read();const first=f.calls.find(path=>path.startsWith('/authoring/history'));
 const query=new URL(first,'http://fixture').searchParams;assert.equal(query.get('file'),'chapter.tex');assert.equal(query.get('correction_category'),'applied-edits');assert.equal(query.get('order'),'newest');assert.equal(query.get('limit'),'25');assert.equal(query.get('offset'),'0');
 assert.ok(f.calls.some(path=>path.includes('id=AC-latest')));assert.equal(f.calls.some(path=>path.startsWith('/authoring/state')),false);
 await f.context.read({historyOlder:true});const history=f.calls.filter(path=>path.startsWith('/authoring/history'));const continuation=new URL(history[1],'http://fixture').searchParams;assert.equal(continuation.get('offset'),'25');assert.equal(continuation.get('as_of'),'cut-exact');assert.ok(f.calls.some(path=>path.includes('id=AC-older')));
});
test('changed history cut preserves comparison and does not silently restart pagination',async()=>{
 const f=fixture();await f.context.read();const before=f.clears(),calls=f.calls.length;f.reject();await f.context.read({historyOlder:true});assert.equal(f.clears(),before);
 const newHistory=f.calls.slice(calls).filter(path=>path.startsWith('/authoring/history'));assert.equal(newHistory.length,1);assert.match(newHistory[0],/offset=25/);assert.match(f.events.at(-1)[1].text,/preserved/);assert.equal(typeof f.events.at(-1)[1].retry,'function');
});
