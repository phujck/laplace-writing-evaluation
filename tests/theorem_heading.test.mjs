import {test} from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
import {walkSource} from './helpers/walk_source.mjs';
const source=walkSource(),start=source.indexOf("    if(kind==='theorem'&&b.theorem_label){"),end=source.indexOf("    const body=el('div','environment-body');",start);
const render=new Function('b','heading','map','host','el','asChrome','renderPiecesMapped',"const kind='theorem';\n"+source.slice(start,end));
const node=(tag,cls,text='')=>({tag,className:cls,textContent:text,children:[],setAttribute(name,value){this[name]=value;},appendChild(child){this.children.push(child);}});
const text=node=>node.textContent+node.children.map(text).join('');
test('declared theorem heading uses display label then actual number and keeps the optional title source editable',()=>{
 const piece={t:'text',s:'Deterministic factorisation',o_start:21,o_end:46},b={env:'arbitraryName',title:'Deterministic factorisation',theorem_label:'Theorem',theorem_optional_title:true,title_pieces:[piece],number:'2.4'},heading=node('strong'),map=[];
 render(b,heading,map,node('div'),node,element=>{element.chrome=true;return element;},(pieces,parent,mapping)=>{for(const piece of pieces){mapping.push(piece);parent.appendChild(node('span',null,piece.s));}});
 assert.equal(text(heading),'Theorem 2.4 (Deterministic factorisation)');assert.deepEqual(map,[piece]);assert.equal(heading.children[0].contenteditable,'false');assert.equal(heading.children[2].chrome,undefined);assert.equal(piece.o_start,21);
});
test('no compiled number means no invented counter and an untitled theorem has only its declared name',()=>{
 for(const [b,expected] of [[{theorem_label:'Proposition',theorem_optional_title:false,title:'arbitraryName'},'Proposition'],[{theorem_label:'Exercise',theorem_optional_title:true,title:'A task',title_pieces:[]},'Exercise (A task)']]){const heading=node('strong');render(b,heading,[],node('div'),node,element=>element,()=>{});assert.equal(text(heading),expected);}
});
