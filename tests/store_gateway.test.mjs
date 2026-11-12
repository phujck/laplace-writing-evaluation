import assert from 'node:assert/strict';
import {test} from 'node:test';
import {Store} from '../src/laplace/web/static_shared/store.mjs';

test('shared same-origin writing POST routes use the gateway identity; reads and foreign origins do not',async()=>{
  const previous=globalThis.fetch,seen=[];
  globalThis.fetch=async(url,init)=>{seen.push({url,init});return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>({ok:true})};};
  try{
    const store=new Store();
    await store.fetchJSON('/authoring/block-change',{method:'POST',body:{project:'book',operation:'delete'}});
    await store.fetchJSON('/authoring/block-change',{method:'POST',body:{project:'book',operation:'undo'}});
    await store.fetchJSON('/authoring/change-preview',{params:{project:'book',file:'chapter.tex'}});
    assert.equal(seen[0].init.headers['X-Laplace-Writing'],'1');
    assert.equal(seen[1].init.headers['X-Laplace-Writing'],'1');
    assert.equal(seen[2].init.headers['X-Laplace-Writing'],undefined);
    assert.equal(JSON.parse(seen[0].init.body).operation,'delete');
    for(const prefix of ['research','references','formal','projects','work','concepts','visuals']){
      await store.fetchJSON('/'+prefix+'/change',{method:'POST',body:{project:'book'}});
      assert.equal(seen.at(-1).init.headers['X-Laplace-Writing'],'1');
    }
    for(const path of ['/work/structure','/work/../work/structure?view=summary','https://elsewhere.invalid/work/change','//elsewhere.invalid/authoring/turn']){
      await store.fetchJSON(path,{method:path.includes('elsewhere')?'POST':'GET'});
      assert.equal(seen.at(-1).init.headers['X-Laplace-Writing'],undefined);
    }
    await store.fetchJSON('./work/structure/change',{method:'POST',body:{project:'book'}});
    assert.equal(seen.at(-1).init.headers['X-Laplace-Writing'],'1');
    await store.fetchJSON('/unrelated/change',{method:'POST',body:{}});
    assert.equal(seen.at(-1).init.headers['X-Laplace-Writing'],undefined);
  }finally{globalThis.fetch=previous;}
});

test('declared scope composes once through the shared gateway and conflicting explicit coordinates refuse',async()=>{
  const previous=globalThis.fetch,seen=[];
  globalThis.fetch=async(url)=>{seen.push(url);return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>({ok:true})};};
  try{
    const store=new Store();store.set({corpus:'reading-project'});
    await store.fetchJSON('/projection/tex',{params:{corpus:'exact-project',file:'book/main.tex'}});
    await store.fetchJSON('/projection/tex?corpus=exact-project',{params:{corpus:'exact-project',file:'book/main.tex'}});
    await store.fetchJSON('/projection/tex?corpus=exact-project',{params:{file:'book/main.tex'}});
    for(const value of seen){const url=new URL(value,'http://localhost');assert.deepEqual(url.searchParams.getAll('corpus'),['exact-project']);}
    assert.throws(()=>store.fetchJSON('/projection/tex?corpus=A',{params:{corpus:'B'}}),/Conflicting explicit request coordinate/);
    assert.equal(seen.length,3);
    // An already malformed route is never silently cleaned into a valid scope.
    await store.fetchJSON('/projection/tex?corpus=A&corpus=A');
    assert.deepEqual(new URL(seen.at(-1),'http://localhost').searchParams.getAll('corpus'),['A','A']);
    await store.fetchJSON('/projection/tex',{params:{corpus:''}});
    assert.deepEqual([...new URL(seen.at(-1),'http://localhost').searchParams],[['corpus','']]);
    await store.fetchJSON('/authoring/document',{params:{project:''}});
    assert.deepEqual([...new URL(seen.at(-1),'http://localhost').searchParams],[['project','']]);
    await store.fetchJSON('/authoring/document?project=exact-project');
    assert.deepEqual([...new URL(seen.at(-1),'http://localhost').searchParams],[['project','exact-project']]);
    await store.fetchJSON('/projection/tex?corpus=');
    assert.deepEqual([...new URL(seen.at(-1),'http://localhost').searchParams],[['corpus','']]);
    assert.equal(store._withParams('/projection/tex',{params:{corpus:null,file:''}}),'/projection/tex?corpus=reading-project');
    store.set({node:'reading-node'});
    assert.deepEqual([...new URL(store._withParams('/node',{inject:['node'],params:{node:''}}),'http://localhost').searchParams],[['node','']]);
    assert.match(store._withParams('/projection/tex?file=main.tex#anchor',{}),/corpus=reading-project#anchor$/);
  }finally{globalThis.fetch=previous;}
});
