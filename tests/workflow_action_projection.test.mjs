// Focused projection control; actual scope method, inert DOM and conversation services.
import {test} from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
const override=process.env.HUMAN_ACTION_SCOPE_SOURCE;
if(override&&!override.startsWith('/tmp/laplace-programme-20261025/human-action-context-consumer/'))throw Error('Assigned correction source required');
const source=await readFile(override||new URL('../src/laplace/web/static_shared/workspace-session.mjs',import.meta.url),'utf8');
const start=source.indexOf('  scope(){'),end=source.indexOf('\n\n  paintContext(',start);assert.ok(start>0&&end>start);
const scope=new Function('chipRow','return function '+source.slice(start,end).trim())(chips=>({chips}));
test('action-only target has an action chip and no replacement reading control; ordinary reading and clear stay unchanged',()=>{
 const target={replaceChildren(value){this.row=value;},setAttribute(){}};
 const reading={hidden:false},clear={hidden:false},scopeText={},feedback={};const nodes=new Map([['[data-message-target]',target],['[data-use-reading]',reading],['[data-clear-target]',clear],['[data-scope]',scopeText],['[data-response-feedback]',feedback]]);
 let contextCalls=0,selectedCards=0;const s={find:key=>nodes.get(key),paintSelectedAction(){selectedCards++;},paintConnectedObservation(){},paintSelection(){},paintContext(){contextCalls++;},getContext:()=>({surface:'project',label:'Project'}),authoredContext(){return this.messageIntent?.context||{surface:'project',label:'Project'}},messageIntent:{context:{surface:'project',label:'Selected review',workflow_action:{reference:'opaque owner reference'}}}};
 scope.call(s);assert.ok(target.row.chips.some(c=>c.label==='Action context attached'));assert.equal(target.row.chips.some(c=>c.label==='Reading attached'),false);assert.equal(reading.hidden,true);assert.equal(clear.hidden,false);assert.equal(contextCalls,1);assert.equal(selectedCards,1);
 s.messageIntent={context:{surface:'manuscript',label:'A chapter'}};s.selectionOverride={quote:'An attached passage',anchor:{file:'chapter.tex'}};scope.call(s);assert.ok(target.row.chips.some(c=>c.label==='Passage attached · chapter.tex'));assert.equal(reading.hidden,false);assert.equal(clear.hidden,false);
 s.selectionOverride=null;s.messageIntent={context:{surface:'structure',label:'Argument'}};scope.call(s);assert.ok(target.row.chips.some(c=>c.label==='Reading attached'));assert.equal(reading.hidden,false);
 s.messageIntent=null;scope.call(s);assert.equal(reading.hidden,false);assert.equal(clear.hidden,true);assert.ok(target.row.chips.some(c=>c.label==='No reading attached'));
});
