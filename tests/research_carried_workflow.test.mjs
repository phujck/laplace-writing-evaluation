// Production controller/typed-response seam. No owner effects, browser or CSS-layout claim.
import test from 'node:test';
import assert from 'node:assert/strict';
import {installHTMLDocument} from './helpers/html_dom.mjs';
import {mountResearchWorkbench} from '../src/laplace/web/static_shared/research-workbench.mjs';

const pin='sha256:'+'a'.repeat(64),scope={kind:'owned-workspace'},scope_id='public-carried-scope';
const manifestRef={schema_version:'laplace.reference/1',owner:'domain.projects',kind:'artifact',identity:{project:'book',id:'ART-public-manifest'}};
const ref=id=>({schema_version:'laplace.reference/1',owner:'pipeline.workflow',kind:'workflow-definition',identity:{id},version:{definition_revision:pin}});
const ids=['WDEF-'+'1'.repeat(32),'WDEF-'+'2'.repeat(32)];
const discovery=payload=>({http:{method:'GET',url:'/work/discovery?'+new URLSearchParams(Object.entries(payload).map(([k,v])=>[k,typeof v==='object'?JSON.stringify(v):v]))}});
const read=id=>({http:{method:'GET',url:'/work/workflow-definitions?'+new URLSearchParams({definition_id:id,version:pin,project_lens:'book'})}});
const library={http:{method:'GET',url:'/work/workflow-definitions?project_lens=book'}};
const body={schema_version:'laplace.workflow-definition/1',title:'Carried method',description:'Exact public purpose',settings:{},layout:{},edges:[],steps:[{id:'author',title:'Author',parent_id:null,assignment:{role:'builder',instructions:'Original instructions Ω',settings:{}}}]};
function saved(id){return {schema_version:body.schema_version,scope_id,scope,definition_id:id,version:pin,head_revision:pin,is_current:true,definition:structuredClone(body),reference:ref(id),read:read(id),current_read:read(id),effective_settings:{},pins:{prepared:[]},actions:{save:{permitted:true,http:{method:'POST',url:'/work/workflow-definitions/save'},payload:{definition_id:id,expected_revision:pin}}}};}
function envelope(selected=false){return {schema_version:'laplace.object-facets/1',view:selected?'object':'workspace',subject:selected?manifestRef:null,basis:pin,scope_id,scope,facets:{purpose:{state:'AVAILABLE',value:{title:selected?'Public manifest':'Research workspace',summary:'Selected public definition custody'}},standing:{state:'AVAILABLE',value:{label:'CURRENT_AT_READ'}},actions:{state:'AVAILABLE',items:selected?[{id:'inspect-handover',title:'Inspect selected handover',permitted:true,read:discovery({facet:'handover',reference:manifestRef})}]:[]}},items:[],coverage:{state:'SELECTED_OWNER_READ',known:0,omitted:0},pagination:{},workflow_library:{permitted:true,read:library,adapter:{kind:'workflow-definition-editor'}}};}
async function setup(){
  const dom=installHTMLDocument(),host=document.createElement('main');document.body.append(host);
  // Match the browser's focusin signal while retaining the HTML DOM test seam.
  const create=document.createElement;document.createElement=tag=>{const node=create(tag),focus=node.focus.bind(node);node.focus=options=>{focus(options);document.dispatchEvent({type:'focusin',target:node});};return node;};
  const calls=[],manifest={schema_version:'laplace.research-handover/1',scope_id,project:'book',reference:manifestRef,basis:pin,entries:ids.map(id=>({class:'included',reference:ref(id),basis:pin,currentness:'CURRENT',frozen_read:read(id),adapter:{kind:'workflow-definition-editor',reference:ref(id)}})),actions:[],qualification:'Selected exact retained versions; not execution authority.'};
  const request=async(url,payload)=>{calls.push({url,payload});assert.equal(payload,undefined,'no Save, export, provider or owner effect');const u=new URL(url,'http://local');if(u.pathname==='/work/workflow-definitions')return u.searchParams.has('definition_id')?saved(u.searchParams.get('definition_id')):{scope_id,scope,definitions:ids.map(id=>({definition_id:id,title:'Carried method',reference:ref(id),read:read(id)})),actions:{}};if(u.searchParams.get('facet')==='handover')return manifest;return envelope(u.searchParams.get('facet')==='object');};
  const controller=await mountResearchWorkbench(host,{request,parameters:new URLSearchParams()});
  await controller.state.read(discovery({facet:'object',reference:manifestRef}),manifestRef);
  const main=host.querySelector('.rw-content'),inspect=main.querySelectorAll('button').find(n=>n.textContent==='Inspect selected handover');inspect.focus();await inspect.onclick();
  return {host,main,controller,manifest,calls,restore(){controller.destroy();dom.restore();}};
}
const buttons=(root,label)=>root.querySelectorAll('button').filter(n=>n.textContent===label);
async function open(s,index=0){const opener=buttons(s.main,'Read carried copy')[index];opener.focus();await opener.onclick();assert.ok(s.main.querySelector('.workflow-editor'),'native editor mounted');return opener;}

test('Back reconstructs the exact carried opener after reordered equal labels and preserves native Unicode draft/guard',async t=>{
  const s=await setup();try{
    const old=await open(s,1),expected=old.dataset.rwFocus;
    await s.main.querySelector('[data-node=author]').onclick();await buttons(s.main,'Instructions')[0].onclick();
    const field=s.main.querySelector('textarea[name=Instructions]');field.value='Carry exact Ω / α → β; never save';await field.oninput();
    // Reordering the typed parent response must not turn an ordinal into identity.
    s.manifest.entries.reverse();const back=buttons(s.main,'Back to object')[0];back.focus();await back.onclick();
    const current=buttons(s.main,'Read carried copy').find(n=>n.dataset.rwFocus===expected);
    assert.ok(current&&current!==old&&current.isConnected);assert.equal(old.isConnected,false);assert.equal(document.activeElement,current);
    await current.onclick();await s.main.querySelector('[data-node=author]').onclick();await buttons(s.main,'Instructions')[0].onclick();
    assert.equal(s.main.querySelector('textarea[name=Instructions]').value,field.value);
    const stored=JSON.parse(sessionStorage.getItem('laplace:workflow-drafts:'+scope_id));assert.equal(stored.drafts[0].basis.payload.expected_revision,pin);
    assert.ok(s.calls.every(row=>row.payload===undefined));
    t.diagnostic(JSON.stringify({request_seam_reads:s.calls.length,POSTs:0,exact_current_opener:true,Unicode_draft_and_guard:true}));
  }finally{s.restore();}
});

test('A detached Back cannot repaint a later parent context or take its focus',async t=>{
  const s=await setup();try{
    await open(s);const old=buttons(s.main,'Back to object')[0];s.controller.state.setTab('overview');
    const before=s.main.textContent,other=document.createElement('button');document.body.append(other);other.focus();await old.onclick();
    assert.equal(s.main.textContent,before);assert.equal(document.activeElement,other);assert.equal(s.controller.state.snapshot().tab,'overview');
    t.diagnostic(JSON.stringify({request_seam_reads:s.calls.length,POSTs:0,detached_return_ignored:true}));
  }finally{s.restore();}
});

test('Explicit return preserves later focus outside the native editor',async t=>{
  const s=await setup();try{
    await open(s);const back=buttons(s.main,'Back to object')[0],other=document.createElement('button');document.body.append(other);other.focus();await back.onclick();
    assert.equal(document.activeElement,other);assert.ok(buttons(s.main,'Read carried copy').length);
    t.diagnostic(JSON.stringify({request_seam_reads:s.calls.length,POSTs:0,later_focus_preserved:true}));
  }finally{s.restore();}
});
