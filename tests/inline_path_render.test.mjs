import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {walkSource} from './helpers/walk_source.mjs';
const source=walkSource();

test('existing code renderer displays a literal path without activating a link or macro',()=>{
  const body={children:[],appendChild(value){this.children.push(value);return value;}};
  const renderSource=source.slice(source.indexOf('function renderPiece('),source.indexOf('function renderPieces('));
  const el=(tag,className='',text='')=>({tag,className,text,children:[],appendChild(value){this.children.push(value);return value;}});
  const appendSource=source.slice(source.indexOf('function appendText('),source.indexOf('function citeNode('));
  const document={createTextNode:text=>({text})},D={unknown:0};
  const render=new Function('el','document','D',appendSource+renderSource+'\nreturn renderPiece;')(el,document,D);
  const literal=String.raw`https://example.invalid/a_b/100%/C:\file/<literal>`;
  render({t:'code',s:literal,command:'path',literal:true,o_start:9,o_end:100},body);
  assert.equal(body.children.length,1);
  assert.equal(body.children[0].tag,'code');
  assert.equal(body.children[0].children[0].text,literal);
  assert.equal(body.children[0].href,undefined);
  assert.equal(D.unknown,0);
  const ordinary={children:[],appendChild(value){this.children.push(value);return value;}};
  render({t:'code',s:String.raw`\scientificCommand`},ordinary);
  assert.equal(D.unknown,1,'ordinary unsupported code retains its existing marked-source behavior');
  render({t:'raw',s:String.raw`\path*{unmapped}`,reason:'Unsupported inline path.'},ordinary);
  assert.equal(ordinary.children[1].title,'Unsupported inline path.');
});

test('literal path keeps existing atomic mapping: exact edges and honest substring refusal',()=>{
  const start=source.indexOf('function pieceEdge('),end=source.indexOf('/** the map inverted.',start);
  const edge=new Function('stickySpan',source.slice(start,end)+'\nreturn pieceEdge;')(()=>{throw Error('No prose inversion may run for a literal path.');});
  const piece={t:'code',rStart:10,rEnd:30,oStart:15,oEnd:41,rText:'C:\\file_name%20.json'};
  assert.equal(edge(piece,'source',10,false),15);
  assert.equal(edge(piece,'source',30,true),41);
  assert.deepEqual(edge(piece,'source',17,false),{refused:'piece'});
});
