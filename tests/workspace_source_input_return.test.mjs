// Source-input parent return only. Typed public response seam, no owner/browser
// proof or network. The real route/pin/body/layout groups are retained separately.
import test from 'node:test';import assert from 'node:assert/strict';
import {installHTMLDocument} from './helpers/html_dom.mjs';
import {openSourceInspector} from '../src/laplace/web/static_shared/workspace-source-inspector.mjs';
import {resetSharedInspector} from '../src/laplace/web/static_shared/workspace-inspector.mjs';
const pin='sha256:'+'a'.repeat(64),basis='sha256:'+'b'.repeat(64),reference={schema_version:'laplace.reference/1',owner:'core.identity',kind:'subsystem',identity:{id:'domain.work'}};
const request={facet:'source-inventory',reference,projection:'inputs',project_lens:'public'},handle={request,http:{method:'GET',url:'/work/discovery?'+new URLSearchParams({...request,reference:JSON.stringify(reference)})}};
function row(path){const target={owner:'repository',repository:'public-source',path},payload={action:'read',repository:target.repository,path,expected_sha256:pin,offset:0,limit:2000},url='/projects/material-references?'+new URLSearchParams({project:'public',view:'preview',target:JSON.stringify(target),expected_sha256:pin,offset:0,limit:2000});return {path,sha256:pin,roles:['source-code'],read:{operation:'repository',payload,http:{method:'GET',url},human_read:{kind:'material-source',project:'public',url}}};}
const rows=[row('src/public/one.py'),row('src/public/two.py')],inventory=()=>({schema_version:'laplace.source-owner-inventory/1',projection:'inputs',state:'AVAILABLE',reference,basis,items:structuredClone(rows),coverage:{known:2,returned:2,qualification:'Public input metadata only.'},contracts:[],capabilities:[],pagination:{next_read:null}});
const dialog=()=>document.body.querySelectorAll('dialog').find(d=>d.open),readOne=()=>dialog().querySelectorAll('.source-inspector-card').find(n=>n.querySelector('h3').textContent==='src/public/one.py').querySelector('button');
for(const later of [false,true])test('Input body Close '+(later?'preserves later focus during parent reinspection':'restores exact newly rendered same-label input opener'),async()=>{
 const env=installHTMLDocument();resetSharedInspector();const root=document.createElement('button');root.textContent='Inspect Source';document.body.append(root);root.focus();let count=0,release;const gate=new Promise(resolve=>release=resolve),calls=[];
 try{const read=async(url,payload)=>{assert.equal(payload,undefined);calls.push(url);if(url===handle.http.url){if(++count===2){const value=inventory();value.items.reverse();return later?gate:value;}return inventory();}const target=JSON.parse(new URL(url,'http://local').searchParams.get('target'));return {schema_version:'laplace.material-reference-source/1',project:'public',target,currentness:'UNBOUND',current_revision:pin.slice(7),revision:'public-registry',units:'Unicode characters',owner_result:{content:'PUBLIC exact source Ω',next_offset:null}};};
  await openSourceInspector({handle,request:read});const old=readOne();old.focus();await old.onclick();assert.match(dialog().textContent,/PUBLIC exact source Ω/);dialog().close();
  if(later){const next=document.createElement('button');next.textContent='Later explicit intent';dialog().append(next);next.focus();document.dispatchEvent({type:'focusin',target:next});release(inventory());await Promise.resolve();await Promise.resolve();assert.equal(document.activeElement,next);}
  else{await Promise.resolve();await Promise.resolve();assert.equal(document.activeElement,readOne());assert.notEqual(document.activeElement,old);assert.equal(old.isConnected,false);assert.equal(calls.length,3);}
  dialog().close();assert.equal(document.activeElement,root);
 }finally{resetSharedInspector();env.restore();}
});
