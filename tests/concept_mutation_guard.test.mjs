import {beforeEach,test} from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
import {conceptChangeGuard,mountMathematicsEditor} from '../src/laplace/web/static_shared/concept-reader.mjs';
const readerURL=new URL('../src/laplace/web/static_shared/concept-reader.mjs',import.meta.url).href;
const source=(await readFile(new URL('../src/laplace/web/static_shared/concept-explorer.mjs',import.meta.url),'utf8')).replace(/^import .*;\n/gm,'');
const prefix=`import {declareControl} from '${new URL('../src/laplace/web/static_shared/workspace-presentation.mjs',import.meta.url).href}';import {renderConceptRecord,scientificText,mountMathematicsEditor,displayLabel,displayConceptKind,statementDisplayTex,conceptReferenceSourceIndex,conceptChangeGuard} from '${readerURL}';const layoutConceptricGraph=()=>({});const renderResearchCard=()=>{};`;
const {mountConceptExplorer}=await import('data:text/javascript;base64,'+Buffer.from(prefix+source).toString('base64'));
class Node {
 constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this._text='';this.value='';this.checked=false;this.isConnected=true;this.classList={add(){},remove(){},toggle(){}};}
 set textContent(value){this._text=String(value||'');this.children=[];}get textContent(){return this._text+this.children.map(node=>node.textContent).join('');}
 append(...items){for(const item of items){item.parentElement=this;this.children.push(item);}}appendChild(item){this.append(item);return item;}insertBefore(item,reference){const at=this.children.indexOf(reference);item.parentElement=this;if(at<0)this.children.push(item);else this.children.splice(at,0,item);return item;}replaceChildren(...items){this._text='';this.children=[];this.append(...items);}
 setAttribute(name,value){this.attrs[name]=String(value);}remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(node=>node!==this);}get options(){return this.children;}
 all(){return [this,...this.children.flatMap(node=>node.all())];}matches(selector){if(selector.startsWith('.'))return this.className.split(' ').includes(selector.slice(1));if(selector.startsWith('[data-'))return selector.slice(6,-1).replace(/-([a-z])/g,(_,c)=>c.toUpperCase()) in this.dataset;return this.tag===selector;}
 querySelector(selector){return this.all().slice(1).find(node=>selector.split(',').some(part=>node.matches(part)))||null;}focus(){}scrollIntoView(){}
}
beforeEach(()=>{globalThis.document={createElement:tag=>new Node(tag),createTextNode:text=>{const node=new Node('#text');node.textContent=text;return node;},head:new Node('head'),body:new Node('body'),querySelector:()=>null};globalThis.window={katex:{render(){}}};});
const focused={id:'support:reading',kind:'support',label:'Reading',summary:'Existing meaning.',projection:{title:'Old title'}};
const state=(local=true,revision='global-1',mutation='node-1')=>({revision,content_revision:mutation,...(local?{mutation_revision:mutation}:{}),focus:focused,relations:[],neighbors:[]});
const submit={preventDefault(){}};

test('local guards require an explicit server capability and the exact focused node',()=>{
 for(const operation of ['edit_node','set_source','set_projection','set_mathematics','set_kind','set_status'])assert.deepEqual(conceptChangeGuard(state(),focused.id,operation),{mutation_revision:'node-1'});
 assert.deepEqual(conceptChangeGuard(state(false),focused.id,'edit_node'),{base_revision:'global-1'});assert.deepEqual(conceptChangeGuard(state(),'other:node','edit_node'),{base_revision:'global-1'});assert.deepEqual(conceptChangeGuard({...state(),mutation_revision:''},focused.id,'edit_node'),{base_revision:'global-1'});
 for(const operation of ['add_edge','remove_edge','retype_edge','add_node','move_node','set_spine','unset_spine'])assert.deepEqual(conceptChangeGuard(state(),focused.id,operation),{base_revision:'global-1'});
});

test('the human mathematics form sends the local guard, falls back on old servers and preserves a conflicting draft',async()=>{
 for(const local of [true,false]){const host=new Node(),calls=[],saved=[];mountMathematicsEditor(host,{node:focused,state:state(local),record:{authored:{statement_tex:'Original statement.'}},project:'p',request:async(path,payload)=>{calls.push(payload);throw Error('mutation revision conflict');},onSaved:()=>saved.push(true)});const form=host.querySelector('form'),statement=form.all().find(node=>node.name==='statement');statement.value='Author revised statement.';await form.onsubmit(submit);assert.equal(calls.length,1);assert.equal(calls[0][local?'mutation_revision':'base_revision'],local?'node-1':'global-1');assert.equal(Object.hasOwn(calls[0],local?'base_revision':'mutation_revision'),false);assert.equal(statement.value,'Author revised statement.');assert.ok(form.textContent.includes('mutation revision conflict'));assert.equal(saved.length,0);}
});
async function explorer({local=true,conflict=false,relations=[]}={}){
 const host=new Node(),calls=[],navigated=[],errors=[],initial={...state(local),relations,neighbors:[{id:'premise',label:'Premise',kind:'postulate'}]};
 const request=async(path,payload)=>{if(path.startsWith('/concepts/history?'))return {basis:{reason:'Exact authored history'},history:[],impact:{objects:[]},pagination:{}};if(path==='/concepts/change'){calls.push(payload);if(conflict&&payload.operation==='edit_node')throw Error('mutation revision conflict');return {state:state(local,'global-'+(calls.length+1),'node-'+(calls.length+1))};}throw Error(path);};
 await mountConceptExplorer(host,{project:'p',data:{current:{...focused,grade:0},root_id:focused.id,children_total:0,children:[],identity_chain:[],navigation:{},dependencies:{}},recordState:initial,logicalPlan:{objects:[]},request,navigate:query=>navigated.push(query),onFocus:()=>{},discuss:()=>{},onError:error=>errors.push(error)});
 return {host,calls,navigated,errors};
}
test('title then description uses the exact returned local guard for the second human write',async()=>{
 for(const local of [true,false]){const {host,calls,navigated}=await explorer({local});const form=host.querySelector('.concept-description-editor').querySelector('form');form.querySelector('input').value='New short title';form.querySelector('textarea').value='New meaning.';await form.onsubmit(submit);assert.deepEqual(calls.map(row=>[row.operation,row.mutation_revision||row.base_revision]),[['set_projection',local?'node-1':'global-1'],['edit_node',local?'node-2':'global-2']]);assert.ok(calls.every(row=>Object.hasOwn(row,'mutation_revision')!==Object.hasOwn(row,'base_revision')));assert.equal(navigated.length,1);}
});
test('an intervening meaning conflict is visible without a hidden retry or discarded text',async()=>{
 const {host,calls,navigated,errors}=await explorer({conflict:true});const form=host.querySelector('.concept-description-editor').querySelector('form');form.querySelector('input').value='New short title';form.querySelector('textarea').value='Unsaved meaning.';await form.onsubmit(submit);assert.equal(calls.length,2);assert.equal(form.querySelector('textarea').value,'Unsaved meaning.');assert.match(form.textContent,/Title saved; description is still unsaved/);assert.deepEqual(errors,['mutation revision conflict']);assert.equal(navigated.length,0);
});
test('human relationship edits continue to guard the whole structural state',async()=>{
 const {host,calls}=await explorer({relations:[{source:focused.id,target:'premise',rel:'prerequisite',rationale:'Required premise.'}]});const form=host.querySelector('.concept-relationship').querySelector('form');await form.onsubmit(submit);assert.equal(calls.length,1);assert.equal(calls[0].operation,'retype_edge');assert.equal(calls[0].base_revision,'global-1');assert.equal(Object.hasOwn(calls[0],'mutation_revision'),false);
});
