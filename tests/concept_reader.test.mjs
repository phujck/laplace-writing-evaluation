import test from 'node:test';
import assert from 'node:assert/strict';

import {
  displayLabel,
  relationshipLabel,
  statementDisplayTex,
  formalAssumptionPosture,
  formalTargetIndex,
  normalizeScientificProse,
  scientificText,
  scientificLimitations,
  mountMathematicsEditor,
} from '../src/laplace/web/static_shared/concept-reader.mjs';

test('scientific limitations preserve prose and separate authored list items',()=>{
  assert.deepEqual(scientificLimitations('Finite sampled range.'),{
    kind:'prose',text:'Finite sampled range.'});
  assert.deepEqual(scientificLimitations(['Finite sampled range.','Not a historical reproduction.']),{
    kind:'list',items:['Finite sampled range.','Not a historical reproduction.']});
  assert.deepEqual(scientificLimitations([]),{kind:'list',items:[]});
});

test('formal target index filters concise rows and joins current receipt status',()=>{
  const targets=[
    {id:'thm:a',label:'Source theorem',statement_tex:'A \\to A',statement_origin:'SOURCE',origin_posture:'SOURCE_DOCUMENTED',binding_ready:true},
    {id:'thm:b',label:'Authored theorem',statement_tex:'B \\to B',statement_origin:'AUTHORED',origin_posture:'AUTHOR_ORIGINATED',binding_ready:true},
  ];
  const receipts=[{concept:{id:'thm:a'},proof_status:'CHECKED',stale:true,superseded:false},
                  {concept:{id:'thm:b'},proof_status:'FAILED',superseded:true}];
  assert.deepEqual(formalTargetIndex(targets,receipts,'source').map(row=>[row.target.id,row.status]),[['thm:a','STALE']]);
  assert.deepEqual(formalTargetIndex(targets,receipts,'authored').map(row=>[row.target.id,row.status]),[['thm:b','NOT CHECKED']]);
});

test('formal assumptions distinguish stated, explicit none, source indexing and missing',()=>{
  assert.equal(formalAssumptionPosture({assumptions:[{text:'Finite variance'}]}).state,'STATED');
  assert.equal(formalAssumptionPosture({assumptions:[],assumptions_authored:true}).state,'EXPLICIT_NONE');
  assert.equal(formalAssumptionPosture({assumptions:[],statement_origin:'SOURCE'}).state,'SOURCE_NOT_INDEXED');
  assert.equal(formalAssumptionPosture({assumptions:[],statement_origin:'AUTHORED',qualification:{missing:['explicit assumptions']}}).state,'MISSING');
});

test('displayLabel never promotes a full essence paragraph into navigation', () => {
  assert.equal(displayLabel({id:'thm:log-cost',title:'Log cost theorem'}),'Log cost theorem');
  assert.equal(displayLabel({id:'thm:log-cost',projection:{term:'Logarithmic cost'}}),'Logarithmic cost');
  assert.equal(displayLabel({id:'result:projection',label:'Projection and residual\nA full explanatory paragraph follows.'}),'Projection and residual');
  assert.equal(displayLabel({id:'thm:finite-measure-valued-closure',label:'x'.repeat(140)}),'finite measure valued closure');
});

test('scientific prose unwraps hard line breaks and retains real paragraphs', () => {
  assert.equal(normalizeScientificProse('A source line\ncontinues here.\n\nA new paragraph.'),
    'A source line continues here.\n\nA new paragraph.');
  assert.equal(normalizeScientificProse('First.\\par Second.'),'First.\n\n Second.');
});

test('multiline inline mathematics remains one rendered expression', async () => {
  class Node {
    constructor(tag='',text=''){this.tag=tag;this.textContent=text;this.children=[];this.className='';}
    append(...items){this.children.push(...items);}
  }
  globalThis.document={
    createElement:tag=>new Node(tag),
    createTextNode:text=>new Node('#text',text),
    querySelector:()=>null,
    head:new Node('head'),
  };
  const rendered=[];
  globalThis.window={katex:{render:(source,node,options)=>{rendered.push({source,node,options});}}};
  const host=new Node('div');

  await scientificText(host,'For $a\n + b$ we retain one expression.');

  assert.equal(rendered.length,1);
  assert.equal(rendered[0].source,'a\n + b');
  assert.equal(rendered[0].options.displayMode,false);
  assert.equal(rendered[0].node.className,'concept-inline-math');
  assert.equal(host.children[0].textContent,'For ');
  assert.equal(host.children[2].textContent,' we retain one expression.');
});

test('source text is editable without becoming authored until changed', async () => {
  class Node {
    constructor(tag='',text=''){this.tag=tag;this.textContent=text;this.children=[];this.className='';this.value='';this.checked=false;this.classList={add(){}};}
    append(...items){for(const item of items){if(item&&typeof item==='object')item.parentElement=this;this.children.push(item);}}
    setAttribute(name,value){this[name]=value;}
    querySelector(tag){for(const child of this.children){if(child?.tag===tag)return child;const found=child?.querySelector?.(tag);if(found)return found;}return null;}
  }
  globalThis.document={createElement:tag=>new Node(tag),createTextNode:text=>new Node('#text',text)};
  const host=new Node('div'),calls=[];
  const record={statement_origin:'SOURCE',statement_tex:'Source statement.',
    proof:{status:'SOURCE_UNREVIEWED',text:'Source proof.'},
    source_locations:[{label:'thm:source',statement_tex:'Source statement.'}],
    authored:{sources:[{path:'source.tex',label:'thm:source'}],formal_targets:[]}};
  mountMathematicsEditor(host,{record,node:{id:'thm:source'},state:{revision:'rev'},project:'p',
    request:async(path,payload)=>{calls.push({path,payload});},onSaved:async()=>{}});
  const form=host.querySelector('form'),fields=[];const collect=node=>{if(node?.tag==='textarea')fields.push(node);for(const child of node?.children||[])collect(child);};collect(form);
  const statement=fields.find(field=>field.name==='statement'),proof=fields.find(field=>field.name==='proof');
  assert.equal(statement.value,'Source statement.');
  assert.equal(proof.value,'Source proof.');

  await form.onsubmit({preventDefault(){}});
  assert.equal(Object.hasOwn(calls[0].payload.value,'statement_tex'),false);
  assert.equal(Object.hasOwn(calls[0].payload.value,'proof'),false);
  assert.deepEqual(calls[0].payload.value.sources,record.authored.sources);

  statement.value='Author revised statement.';
  await form.onsubmit({preventDefault(){}});
  assert.equal(calls[1].payload.value.statement_tex,'Author revised statement.');
});

test('non-mathematical canonical source locations appear in the readable source panel',async()=>{
  const {renderConceptRecord}=await import('../src/laplace/web/static_shared/concept-reader.mjs');
  class Node{
    constructor(tag='',text=''){this.tag=tag;this.textContent=text;this.children=[];this.dataset={};this.className='';this.classList={add(){}};}
    append(...items){for(const item of items){if(item&&typeof item==='object')item.parentElement=this;this.children.push(item);}}
    appendChild(item){this.append(item);return item;}
    replaceChildren(...items){this.children=[];this.append(...items);}
    setAttribute(name,value){this[name]=value;}
    all(){return [this,...this.children.flatMap(child=>child?.all?.()||[])];}
  }
  globalThis.document={createElement:tag=>new Node(tag),createTextNode:text=>new Node('#text',text),querySelector:()=>null,head:new Node('head')};
  globalThis.window={katex:{render(){}}};const source={status:'READ',repository:'papers',path:'original.tex',file:'sources/original.tex',line_start:2,line_end:4,sha256:'abc',excerpt:'A resolved original source.'};
  const opened=[],host=new Node('div');const article=await renderConceptRecord(host,{node:{id:'support:source-audit',kind:'support',label:'Source audit',summary:'Original reading provenance.'},state:{source_locations:[source]},onSource:value=>opened.push(value)});
  assert.ok(article.all().some(item=>item.textContent==='A resolved original source.'));
  const open=article.all().find(item=>item.tag==='button'&&item.textContent==='Locate in manuscript');open.onclick();
  assert.deepEqual(opened,[source]);
});


test('bare formula-only statements render as mathematics without changing prose or already delimited source',()=>{
 const formula=String.raw`H(W\mid C)\ge\mathbb E[\ln R_C(W)].`;
 assert.equal(statementDisplayTex(formula),'\\['+formula+'\\]');assert.equal(statementDisplayTex('For every context, $H(W \mid C)$ is finite.'),'For every context, $H(W \mid C)$ is finite.');assert.equal(statementDisplayTex('A valid bound is declared here.'),'A valid bound is declared here.');
 assert.equal(displayLabel({id:'result:identifier',label:'Long scientific meaning '.repeat(8),projection:{title:'Conditional erasure bound'}}),'Conditional erasure bound');
});


test('typed relationship descent labels exact incoming roles instead of one generic inverse',()=>{
 assert.equal(relationshipLabel('prerequisite',false),'Required by');assert.equal(relationshipLabel('support',false),'Supports');assert.equal(relationshipLabel('implementation',false),'Implements');assert.equal(relationshipLabel('contains',false),'Contained by');assert.equal(relationshipLabel('future-type',false),'Incoming future-type');
});
