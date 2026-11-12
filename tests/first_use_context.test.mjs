// Presentation-only assertions over the actual context selector. No owner effects.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {declareControl} from '../src/laplace/web/static_shared/workspace-presentation.mjs';
import {materialReadingInput} from '../src/laplace/web/static_shared/local-document-intake-port.mjs';
const source=await readFile(new URL('../src/laplace/web/static_shared/workspace-session.mjs',import.meta.url),'utf8');
const code=source.slice(source.indexOf('export function nextMessagePreview'),source.indexOf('// workspace-session.mjs'));
const preview=new Function('materialReadingInput',code.replace('export function','function')+';return nextMessagePreview;')(materialReadingInput);
test('project framing is not described as an inspected source; exact Unicode attachment extent is retained without mutation',()=>{
 const framing={surface:'sources',label:'file Ω.txt'},before=structuredClone(framing);assert.equal(preview(framing,null,{project:'p'})[0].kind,'framing');assert.deepEqual(framing,before);
 const intent={surface:'sources',label:'Ω source',material_read:{schema_version:'laplace.material-reading/1',project:'p',artifact_id:'ART-public',sha256:'a'.repeat(64),read_payload:{id:'ART-public',expected_sha256:'a'.repeat(64),offset:6000,limit:4000}}},copy=structuredClone(intent),rows=preview(intent,null,{project:'p'});
 assert.equal(rows[0].kind,'document');assert.match(rows[0].extent,/offset 6000, limit 4000 characters/);assert.deepEqual(rows[0].identity,intent.material_read);assert.deepEqual(intent,copy);
 assert.equal(preview(intent,null,{project:'foreign'})[0].kind,'unavailable');assert.deepEqual(intent,copy);
});
test('explicit passage and object context keep their different meaning and exact words',()=>{
 const text='Complete selected passage — Ω\nα → β 🧪',selection={quote:text,draft:true},object={surface:'source',label:'Selected meaning',object_context:{reference:{kind:'artifact',identity:{id:'exact'}}}};
 const before=structuredClone({object,selection}),rows=preview(object,selection,{project:'p'});assert.deepEqual(rows.map(r=>r.kind),['object','selection']);assert.match(rows[0].extent,/does not imply the whole source/);assert.equal(rows[1].extent,text);assert.deepEqual({object,selection},before);
});

// Recovery-phase presentation boundary: imported sources lead; advanced link
// custody stays in the existing controller and its authored draft remains mounted.
test('source linking is optional, while an existing linking draft or selected link opens its containing disclosure',async()=>{
 const {installDOM,Node}=await import('./helpers/evidence_reader_harness.mjs'),dom=installDOM();
 try{const source=await readFile(new URL('../src/laplace/web/static_shared/workspace-material.mjs',import.meta.url),'utf8'),body=source.slice(source.indexOf('export async function mountMaterial'),source.indexOf('export async function mountTurns')).replace('export async function','async function');
 const el=(tag,text='',cls='')=>{const n=new Node(tag);n.textContent=text;n.className=cls;return n;},mount=new Function('el','action','workspaceViewAvailable','relationList','mountSharedReferences','url','declareControl',body+';return mountMaterial;')(el,()=>el('button'),()=>false,()=>el('div'),async(host,{draft})=>{host.append(el('form','Existing link draft'));return {capture:()=>draft};},()=>'/work/materials',declareControl);
 for(const draft of [null,{path:'Exact/Ω.txt'}]){const host=el('main');dom.body.append(host);const controller=await mount(host,{project:'p',info:{capabilities:{}},draft,request:async()=>({materials:[],pagination:{next_offset:null,total:0}})}),advanced=host.querySelector('.material-link-options');assert.equal(advanced.open,!!draft);assert.ok(advanced.querySelector('form'));assert.deepEqual(controller.capture(),draft);assert.equal(host.children[0].textContent,'Sources');assert.ok(host.textContent.includes('Link another source'));
  // linked material has its own section ahead of the optional linking form; it is never folded behind that form
  const linked=host.querySelector('.material-linked');assert.ok(linked,'linked material section');const order=[...host.children];assert.ok(order.indexOf(linked)<order.indexOf(advanced),'linked material precedes the linking form');}
 }finally{dom.restore();}
});
// Identity-qualified deduplication of linked versus recorded Material: owner, project, scope, path AND revision; never a path alone.
test('a linked reference and a recorded file are the same material only on full identity; a shared path alone never deduplicates',async()=>{
 const material=await readFile(new URL('../src/laplace/web/static_shared/workspace-material.mjs',import.meta.url),'utf8');
 const same=new Function(material.slice(material.indexOf('export function sameMaterialIdentity'),material.indexOf('\nexport function workspaceViewAvailable')).replace('export function','function')+';return sameMaterialIdentity;')();
 const pin='sha256:'+'a'.repeat(64),row={id:'ART-one',path:'notes/Ω.md',scope:'project',recorded_revision:pin},linked=rev=>({id:'MAT-1',target:{owner:'artifact',project:'p',path:'notes/Ω.md',scope:'project'},consumed_revision:rev});
 assert.equal(same(linked(pin),row,{project:'p'}),true);assert.equal(same(linked('a'.repeat(64)),row,{project:'p'}),true,'a bare pin equals its prefixed form');
 assert.equal(same(linked(pin),row,{project:'other'}),false,'same path in another project');assert.equal(same({...linked(pin),target:{...linked(pin).target,scope:'manuscript'}},row,{project:'p'}),false,'another scope');
 assert.equal(same(linked('sha256:'+'b'.repeat(64)),row,{project:'p'}),false,'another revision keeps both records');assert.equal(same(linked(null),row,{project:'p'}),false,'no revision is not an identity');
 assert.equal(same({...linked(pin),target:{owner:'repository',repository:'p',path:'notes/Ω.md'}},row,{project:'p'}),false,'a repository owner is never a recorded file');
 assert.equal(same(linked(pin),{...row,recorded_revision:null},{project:'p'}),false);
});
test('plain intake outcomes preserve unknown/partial/original/link distinctions and never modify receipt data',async()=>{
 const {documentIntakeOutcome,renderLocalDocumentChoice}=await import('../src/laplace/web/static_shared/local-document-intake.mjs');
 const cases=[{state:'UNKNOWN'},{state:'NONE'},{state:'PARTIAL',original:{state:'RETAINED'},membership:{state:'PENDING'}},{state:'RECORDED',original:{state:'RETAINED'},membership:{state:'LINKED'}}],before=structuredClone(cases);assert.match(documentIntakeOutcome(cases[0]),/still unknown/);assert.match(documentIntakeOutcome(cases[1]),/No saved result/);assert.match(documentIntakeOutcome(cases[2]),/Original file saved.*unfinished/);assert.match(documentIntakeOutcome(cases[3]),/saved and available in Sources/);assert.deepEqual(cases,before);
 const {installDOM,Node}=await import('./helpers/evidence_reader_harness.mjs'),dom=installDOM();try{const host=new Node('section');renderLocalDocumentChoice(host,{project:'garden-watering-notes',projectTitle:'Garden watering notes',onChoose(){},onMediaChange(){}});assert.ok(host.textContent.includes('Add to Garden watering notes'));assert.ok(!host.textContent.includes('Add to garden-watering-notes'));}finally{dom.restore();}
});
