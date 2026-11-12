import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../src/laplace/web/static_shared/writing-panel.mjs',import.meta.url),'utf8');
const body=source.slice(source.indexOf('export function bindPassageContext'),source.indexOf('function bootEmbedded()')).replace('export ','');
test('an open passage reader follows selected block while same-block typing makes no owner reads',()=>{
 const listeners={},blocks=[{id:'finite',file:'main.tex',text:'Finite draft'},{id:'scope',file:'main.tex',text:'Scope unsaved draft'}];let selected='finite',held='finite',reads=0,clears=0;const caret={block:'scope',offset:7};
 const walk={on:(name,fn)=>{(listeners[name]??=[]).push(fn);},readingPosition:()=>({blockId:selected}),blocks:()=>blocks};
 const env={};vm.createContext(env);vm.runInContext(body+';this.bind=bindPassageContext;',env);
 env.bind(walk,{current:()=>held,select:block=>{reads++;held=block.id;},clear:()=>{clears++;held=null;}});
 for(let i=0;i<50;i++)listeners.attention.forEach(fn=>fn());assert.equal(reads,0);
 selected='scope';listeners.attention.forEach(fn=>fn());assert.equal(held,'scope');assert.equal(reads,1);
 listeners.section.forEach(fn=>fn());assert.equal(reads,1);
 assert.equal(blocks[1].text,'Scope unsaved draft');assert.deepEqual(caret,{block:'scope',offset:7});
 listeners.bank.forEach(fn=>fn());assert.equal(clears,1);assert.equal(held,null);
 listeners.attention.forEach(fn=>fn());assert.equal(reads,1,'closed/invalidated context does not refetch on typing');
});
