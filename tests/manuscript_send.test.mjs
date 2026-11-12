import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {walkSource} from './helpers/walk_source.mjs';
const source=walkSource();
const body=source.slice(source.indexOf('async function prepareForSession('),source.indexOf('/** Ctrl-S — THE bank'));
function editor(){const a={id:'a',tex:'saved a',bodyEl:{text:'new a'},src:{file:'main.tex',lineStart:2,lineEnd:2}},b={id:'b',tex:'saved b',bodyEl:{text:'new b'},src:{file:'other.tex',lineStart:7,lineEnd:7}};const sandbox={Date,setTimeout,Promise,assignBasis:(t,b)=>Object.assign(t,{tex:b.tex,src:b.src,expectedSelection:b.expectedSelection,expected:b.expected}),captureBasis:b=>({tex:b.tex||'',src:b.src,expectedSelection:undefined,expected:[]}),srcOf:b=>b.src,hostText:e=>e.text,blockById:new Map([['a',a],['b',b]]),E:{blockId:'',dirty:false},F:{},P:new Map([['a',{pristine:'saved a',text:'new a'}],['b',{pristine:'saved b',text:'new b'}]]),RELOAD_INFLIGHT:null,paragraphTransition:null,setEditScope(){},emit(){},parkEdit(){},commits:[]};sandbox.commitEdit=async()=>{const id=sandbox.E.blockId;sandbox.commits.push(id);sandbox.P.delete(id);sandbox.E.dirty=false;};vm.createContext(sandbox);vm.runInContext(body+';this.prepare=prepareForSession;',sandbox);return sandbox;}
test('manuscript Send saves its selected parked passage without touching unrelated drafts',async()=>{const e=editor();await e.prepare({files:['main.tex'],line_start:2,line_end:2});assert.deepEqual(e.commits,['a']);assert.equal(e.P.has('b'),true);});
test('a raw source draft is delivered without being written or treated as saved text',async()=>{const e=editor();e.P.delete('a');e.F={blockId:'a',baseTex:'saved a',ta:{value:'\\invalid{'}};const result=await e.prepare({files:['main.tex'],line_start:2,line_end:2});assert.deepEqual(e.commits,[]);assert.equal(result.draft.status,'UNSAVED');assert.equal(result.draft.format,'tex');assert.equal(result.draft.text,'\\invalid{');});
