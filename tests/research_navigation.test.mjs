import {beforeEach,test} from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
import {register} from 'node:module';register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
// the research navigation helpers are the real facade exports (workspace-research.mjs, M5 S2 F1)
const {researchNavigation,researchNavigationURL,loadResearchNavigation,saveResearchNavigation}=await import('../src/laplace/web/static_shared/workspace.mjs');
const storage=()=>{const values=new Map();return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value))};};
beforeEach(()=>{globalThis.sessionStorage=storage();});
const scoped={subview:'literature',literatureTarget:{claim_id:'result:obstruction',label:'The obstruction',anchor:{file:'chapter.tex',line_start:8,line_end:10}},literatureReader:{key:'doi:10.1234/source',title:'Original source',source_index:1,offset:12000,mode:'text'}};

test('Research never infers claim scope from an unrelated logical node URL',()=>{
 const state=loadResearchNavigation('book',new URLSearchParams('view=research&node=result:old-selection'));assert.equal(state.subview,'numerics');assert.equal(state.literatureTarget,null);assert.equal(state.literatureReader,null);
 const global=researchNavigation(new URLSearchParams('research=literature&node=result:old-selection'));assert.equal(global.literatureTarget,null);
});
test('claim and exact source reader survive reload without carrying the old logical node',()=>{
 saveResearchNavigation('book',scoped);const url=researchNavigationURL('http://localhost/project?view=research&node=result:old',scoped);assert.equal(url.searchParams.has('node'),false);assert.equal(url.searchParams.get('research'),'literature');assert.equal(url.searchParams.get('research_claim'),'result:obstruction');
 const restored=loadResearchNavigation('book',url.searchParams);assert.deepEqual(restored.literatureTarget,scoped.literatureTarget);assert.deepEqual(restored.literatureReader,scoped.literatureReader);assert.equal(restored.subview,'literature');
});
test('Clear claim target removes its URL scope and cannot revive from saved state',()=>{
 saveResearchNavigation('book',scoped);const url=researchNavigationURL('http://localhost/project?view=research&research=literature&research_claim=result:obstruction&research_source=old',{subview:'literature',literatureTarget:null});const restored=loadResearchNavigation('book',url.searchParams);assert.equal(restored.literatureTarget,null);assert.equal(restored.literatureReader,null);assert.equal(url.searchParams.get('research_scope'),'project');
});
test('new tabs without an explicit target open project scope; an explicit other claim cannot inherit an old passage',()=>{
 saveResearchNavigation('book',scoped);globalThis.sessionStorage=storage();const fresh=loadResearchNavigation('book',new URLSearchParams('view=research&research=literature'));assert.equal(fresh.literatureTarget,null);assert.equal(fresh.literatureReader,null);
 const changed=researchNavigation(new URLSearchParams('research=literature&research_claim=result:other'),scoped);assert.deepEqual(changed.literatureTarget,{claim_id:'result:other',label:'result:other'});
});
test('explicit return routes retain Research context while ordinary view changes keep their chosen view',()=>{
 const returnPlace={view:'research',label:'Research',scrollTop:420};saveResearchNavigation('book',{...scoped,returnPlace});const linked=researchNavigationURL('http://localhost/project?view=manuscript',{...scoped,returnToResearch:true},{active:false});assert.equal(linked.searchParams.get('view'),'manuscript');const restored=loadResearchNavigation('book',linked.searchParams);assert.equal(restored.returnToResearch,true);assert.deepEqual(restored.returnPlace,returnPlace);
 const ordinary=researchNavigationURL(linked,{...scoped,returnToResearch:false},{active:false});assert.equal(ordinary.searchParams.get('view'),'manuscript');assert.equal(ordinary.searchParams.has('research_return'),false);assert.equal(ordinary.searchParams.has('research_claim'),false);
});
test('explicit subview is authoritative over this tab’s prior view and URL scope survives restricted storage',()=>{
 saveResearchNavigation('book',scoped);assert.equal(loadResearchNavigation('book',new URLSearchParams('view=research&research=formal')).subview,'formal');globalThis.sessionStorage={getItem(){throw Error('restricted');},setItem(){throw Error('restricted');}};const url=researchNavigationURL('http://localhost/project?view=research',scoped);assert.equal(loadResearchNavigation('book',url.searchParams).literatureTarget.claim_id,'result:obstruction');assert.doesNotThrow(()=>saveResearchNavigation('book',scoped));
});
