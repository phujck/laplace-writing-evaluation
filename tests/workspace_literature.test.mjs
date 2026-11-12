import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {register} from 'node:module';register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
// the research navigation helpers are the real facade exports (workspace-research.mjs, M5 S2 F1)
const {loadResearchNavigation,saveResearchNavigation,researchNavigationURL}=await import('../src/laplace/web/static_shared/workspace.mjs');
import {mountLiterature,groupLibraryRows,scopeSources,safePublisherUrl} from '../src/laplace/web/static_shared/workspace-literature.mjs';

test('a retained source keeps the reader\'s exact claim or passage target in its draft and refuses a malformed one',async()=>{
 const {retainedLiteratureTarget,createRetainedLiteratureDraft}=await import('../src/laplace/web/static_shared/retained-source-literature.mjs');
 const store=()=>{const values=new Map();return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value)};};
 assert.deepEqual(retainedLiteratureTarget({claim_id:'claim:assumption-A',label:'Assumption A'}),{claim_id:'claim:assumption-A',label:'Assumption A'});
 assert.deepEqual(retainedLiteratureTarget({anchor:{file:'main.tex',line_start:3,line_end:4}}),{anchor:{file:'main.tex',line_start:3,line_end:4}});
 assert.equal(retainedLiteratureTarget(null),null);
 for(const bad of [{claim_id:''},{claim_id:'c',anchor:{}},{anchor:[]},{claim_id:'c',meaning_revision:'sha256:x'},{claim_id:'c',label:'x'.repeat(241)},'claim'])
  assert.throws(()=>retainedLiteratureTarget(bad),/one exact claim or manuscript passage/);
 const original={artifact_id:'ART-public',expected_sha256:'sha256:'+'a'.repeat(64)},storage=store(),backup=store();
 const draft=createRetainedLiteratureDraft({project:'public',original,storage,backup});
 draft.update({target:retainedLiteratureTarget({claim_id:'claim:assumption-A'}),values:{title:'Typed title'}});
 const reloaded=createRetainedLiteratureDraft({project:'public',original,storage,backup});
 assert.deepEqual(reloaded.snapshot().target,{claim_id:'claim:assumption-A'});assert.equal(reloaded.snapshot().values.title,'Typed title');
 const other=createRetainedLiteratureDraft({project:'other',original,storage,backup});assert.equal(other.snapshot().target,undefined);
});

class Node{
  constructor(tag,text=''){this.tag=tag;this.ownText=text;this.children=[];this.dataset={};this.attributes={};this.value='';this.events={};}
  set textContent(value){this.ownText=value;this.children=[];}get textContent(){return this.ownText+this.children.map(child=>child.textContent||'').join('');}
  append(...items){for(const item of items){item.parent=this;this.children.push(item);}}
  replaceChildren(...items){this.children=[];this.ownText='';this.append(...items);}
  setAttribute(key,value){this.attributes[key]=value;}
  addEventListener(key,fn){const prior=this.events[key];this.events[key]=event=>{prior?.(event);fn(event);};}
  showModal(){this.open=true;}close(){this.open=false;this.events.close?.();}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);}
  all(){return [this,...this.children.flatMap(child=>child.all?.()||[])];}
}
function dom(){globalThis.document={createElement:tag=>new Node(tag),createTextNode:text=>new Node('#text',text),head:new Node('head'),body:new Node('body'),querySelector:()=>null};const host=new Node('main');document.body.append(host);return host;}
const find=(node,text)=>node.all().find(item=>item.tag==='button'&&item.ownText===text);
const span={file:'paper/manuscript/chapter.tex',line_start:4,line_end:4,character_start:22,character_end:35,instance:0,text:'\\cite{Author}',source_sha256:'current'};
const row={key:'doi:10.1234/source',citekey:'Author',metadata:{title:'A meaningful paper',creators:['A. Author'],year:'2024'},source:{provider:'crossref'},bibliography:{state:'ATTACHED',entry_present:true},state:'CURRENT',claim_id:'claim:law',relation:'supports',rationale:'The argument requires this bounded premise.',reading_status:'partial',evidence_status:'authored-passage',evidence:{locator:'page 4'},manuscript_uses:[span]};

function fakeRequest(log,records=[row]){return async(path,payload)=>{log.push({path,payload});if(path.startsWith('/references/literature-uses'))return {uses:records,pagination:{}};if(path.startsWith('/concepts/catalog'))return {items:[{id:'claim:law',label:'The proposed law',kind:'result'}],next_offset:null};if(path.startsWith('/concepts/state'))return {focus:{id:'claim:law',kind:'result',summary:'The inspected proposed law'},source_support:{meaning_revision:'sha256:meaning-read'}};if(path.startsWith('/references/source'))return {available:false,source_state:'metadata-only',reason:'No local full text.',publisher_url:'https://example.org/paper',bibliography:{state:'ATTACHED',entry_present:true},binding_contract:{target_kinds:['result']}};if(path.startsWith('/references/literature-discover'))return {items:[{title:'New public work',doi:'10.1234/new',creators:['B. Author']}]};if(path==='/references/literature-import')return {association:{...row,key:'local:new',citekey:'NewLocal',metadata:{title:payload.metadata?.title||'New public work'}}};if(path==='/references/literature-bind')return {ok:true,association:payload};throw new Error('Unexpected route '+path);};}

test('source grouping preserves links and deduplicates spans copied across claim associations',()=>{
 const grouped=groupLibraryRows([row,{...row,claim_id:'claim:other'}]);assert.equal(grouped.length,1);assert.equal(grouped[0].claims.length,2);assert.equal(grouped[0].uses.length,1);
 assert.equal(scopeSources(grouped,{claim_id:'missing'},true).length,0);assert.equal(scopeSources(grouped,null,false,'meaningful').length,1);
 assert.equal(safePublisherUrl('javascript:alert(1)'),null);assert.equal(safePublisherUrl('https://example.org/paper'),'https://example.org/paper');
});

test('project library is default, readable uses call exact passage and citation owners, and target removal propagates',async()=>{
 const host=dom(),log=[],opened=[],inserted=[],changed=[];const view=mountLiterature(host,{project:'paper',request:fakeRequest(log),target:{claim_id:'claim:law',label:'The proposed law',anchor:{file:'chapter.tex',line:4}},onOpenPassage:span=>opened.push(span),onInsertCitation:value=>inserted.push(value),onTargetChange:value=>changed.push(value)});await view.ready;
 assert.match(host.textContent,/A meaningful paper/);assert.match(host.textContent,/The argument requires/);assert.match(host.textContent,/The proposed law/);assert.equal(log.some(call=>call.path.includes('literature-discover')),false);
 await find(host,'manuscript/chapter.tex · line 4').onclick();assert.equal(opened[0].source_sha256,'current');
 await find(host,'Insert citation…').onclick();assert.equal(inserted[0].citekey,'Author');assert.equal(inserted[0].citation,'\\cite{Author}');assert.equal(inserted[0].target.claim_id,'claim:law');
 await find(host,'Clear claim target').onclick();assert.deepEqual(changed,[null]);assert.equal(find(host,'Clear claim target'),undefined);
 await find(host,'Insert citation…').onclick();assert.equal(inserted[1].target,null);view.destroy();
});

test('read source displays honest metadata-only status and a publisher link without declaring a read',async()=>{
 const host=dom(),log=[];const view=mountLiterature(host,{project:'paper',request:fakeRequest(log)});await view.ready;
 await find(host,'Read source').onclick();assert.match(document.body.textContent,/No local full text/);assert.match(document.body.textContent,/neither automatically establishes/);assert.equal(document.body.all().find(n=>n.tag==='a').href,'https://example.org/paper');assert.equal(log.some(call=>call.payload),false);view.destroy();
});

test('local source draft survives tab switches and imports explicit provenance without a fabricated DOI',async()=>{
 const host=dom(),log=[];const view=mountLiterature(host,{project:'paper',request:fakeRequest(log,[])});await view.ready;
 await find(host,'Add local source').onclick();let inputs=host.all().filter(n=>n.name);for(const [name,value]of Object.entries({title:'Unpublished book',creators:'A. Author\nB. Author',description:'Author supplied draft',path:'draft/book.pdf',item_type:'book'})){const field=inputs.find(n=>n.name===name);field.value=value;field.oninput();}
 await find(host,'Project library').onclick();await find(host,'Add local source').onclick();inputs=host.all().filter(n=>n.name);assert.equal(inputs.find(n=>n.name==='title').value,'Unpublished book');
 const form=host.all().find(n=>n.tag==='form');await form.onsubmit({preventDefault(){}});const imported=log.find(call=>call.path==='/references/literature-import').payload;
 assert.equal(imported.metadata.title,'Unpublished book');assert.deepEqual(imported.metadata.creators,['A. Author','B. Author']);assert.equal(imported.provenance.path,'draft/book.pdf');assert.equal(imported.provenance.description,'Author supplied draft');assert.equal('doi' in imported,false);view.destroy();
});

test('Crossref discovery saves a verified DOI through the canonical import operation',async()=>{
 const host=dom(),log=[];const view=mountLiterature(host,{project:'paper',request:fakeRequest(log,[])});await view.ready;await find(host,'Discover sources').onclick();const input=host.all().find(n=>n.name==='query');input.value='New public';input.oninput();const form=host.all().find(n=>n.tag==='form');await form.onsubmit({preventDefault(){}});await find(host,'Verify DOI & save to library').onclick();assert.equal(log.find(call=>call.path==='/references/literature-import').payload.doi,'10.1234/new');view.destroy();
});

test('empty claim starts with agent delegation and still shows existing project sources',async()=>{
 const host=dom(),delegated=[];const base=fakeRequest([], [row]);const request=async(path,payload)=>path.includes('claim_id=claim%3Aopen')?{uses:[],pagination:{}}:base(path,payload);
 const view=mountLiterature(host,{project:'paper',request,target:{claim_id:'claim:open',label:'An open scientific claim'},onDiscuss:(prompt,target)=>delegated.push({prompt,target})});await view.ready;
 assert.match(host.textContent,/Existing project sources to examine/);assert.match(host.textContent,/A meaningful paper/);
 await find(host,'Find literature for this claim').onclick();assert.equal(delegated[0].target.claim_id,'claim:open');assert.match(delegated[0].prompt,/claim:open/);assert.match(delegated[0].prompt,/read available source passages/);assert.match(delegated[0].prompt,/unsupported claims visibly open/);view.destroy();
});


test('manual binding reads an exact passage in place and passes its observation handle',async()=>{
 const host=dom(),log=[],base=fakeRequest(log);const request=async(path,payload)=>{
  if(path.startsWith('/references/text'))return {source_state:'extracted',text:'A bounded controlled passage.',reading_receipt:{id:'READ-1',locator:'characters 0–29'}};
  return base(path,payload);
 };
 const view=mountLiterature(host,{project:'paper',request,target:{claim_id:'claim:law',label:'The proposed law'}});await view.ready;
 await find(host,'Link / review for this claim').onclick();await find(host,'Read source passage here').onclick();
 const dialog=host.all().find(n=>n.tag==='dialog'),form=dialog.all().find(n=>n.tag==='form');
 assert.match(dialog.textContent,/A bounded controlled passage/);assert.match(dialog.textContent,/returned passage is recorded/);
 form.all().find(n=>n.name==='reading_status').value='partial';await form.onsubmit({preventDefault(){}});
 const bound=log.find(call=>call.path==='/references/literature-bind').payload;
 assert.equal(bound.reading_id,'READ-1');assert.equal(bound.reading_status,'partial');view.destroy();
});


test('discovery retains local candidates when public search is unavailable',async()=>{
 const host=dom(),base=fakeRequest([],[]);const request=async(path,payload)=>path.startsWith('/references/literature-discover')?{items:[],public_state:'UNAVAILABLE',public_error:'Public search timed out.',local_candidates:[{title:'Existing local book',authors:['Local Author'],year:2025,cand_id:'corpus:book',provenance:'reference_corpus'}]}:base(path,payload);
 const view=mountLiterature(host,{project:'paper',request});await view.ready;await find(host,'Discover sources').onclick();host.all().find(n=>n.name==='query').value='book';await host.all().find(n=>n.tag==='form').onsubmit({preventDefault(){}});
 assert.match(host.textContent,/Existing local book/);assert.match(host.textContent,/Public search timed out/);await find(host,'Review local metadata').onclick();
 assert.equal(host.all().find(n=>n.name==='title').value,'Existing local book');assert.match(host.all().find(n=>n.name==='description').value,/corpus:book/);view.destroy();
});


test('claim-scoped source reading reloads its selected source/offset and closes back to the same claim',async()=>{
 const values=new Map();globalThis.sessionStorage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value))};let navigation={subview:'literature',literatureTarget:{claim_id:'claim:law',label:'The proposed law'},literatureReader:null},url=new URL('http://localhost/project?view=research');
 const save=()=>{saveResearchNavigation('paper',navigation);url=researchNavigationURL(url,navigation);};save();const log=[],base=fakeRequest(log);const request=async(path,payload)=>{if(path.startsWith('/references/source')){log.push({path,payload});return {available:true,kind:'text',sources:[{index:0,label:'Original'},{index:1,label:'Authored reading note'}]};}if(path.startsWith('/references/text')){log.push({path,payload});const q=new URL(path,'http://localhost').searchParams,offset=Number(q.get('offset'));return {source_state:'extracted',text:'Exact passage at '+offset+' from source '+q.get('source_index'),next_offset:offset?null:12000};}return base(path,payload);};
 const options=()=>({project:'paper',request,target:navigation.literatureTarget,reader:navigation.literatureReader,onDiscuss(){},onReaderChange:value=>{navigation.literatureReader=value;save();},onTargetChange:value=>{navigation.literatureTarget=value;navigation.literatureReader=null;save();}});
 let host=dom(),view=mountLiterature(host,options());await view.ready;await find(host,'Read source').onclick();const chooser=host.all().find(node=>node.name==='source_index');chooser.value='1';await chooser.onchange();await find(host,'Read next passage').onclick();assert.equal(navigation.literatureReader.offset,12000);assert.equal(navigation.literatureReader.source_index,1);view.destroy();
 navigation=loadResearchNavigation('paper',url.searchParams);host=dom();view=mountLiterature(host,options());await view.ready;assert.match(host.textContent,/Exact passage at 12000 from source 1/);assert.match(host.textContent,/The proposed law/);assert.equal(navigation.literatureTarget.claim_id,'claim:law');await find(host,'Close').onclick();assert.equal(navigation.literatureReader,null);assert.equal(navigation.literatureTarget.claim_id,'claim:law');assert.ok(find(host,'Find literature for this claim'));assert.equal(url.searchParams.has('research_source'),false);
 await find(host,'Clear claim target').onclick();assert.equal(navigation.literatureTarget,null);assert.equal(url.searchParams.has('research_claim'),false);assert.ok(find(host,'Find literature for this project'));assert.ok(!log.some(call=>call.payload));view.destroy();
});


test('closing a pending source read cannot revive its cleared navigation state',async()=>{
 const host=dom(),reader=[],log=[],base=fakeRequest(log);let release;const request=(path,payload)=>path.startsWith('/references/source')?new Promise(resolve=>{release=()=>resolve({available:true,kind:'text'});}):base(path,payload);
 const view=mountLiterature(host,{project:'paper',request,target:{claim_id:'claim:law',label:'The proposed law'},onReaderChange:value=>reader.push(value)});await view.ready;const pending=find(host,'Read source').onclick();await find(host,'Close').onclick();assert.equal(reader.at(-1),null);release();await pending;assert.equal(reader.at(-1),null);assert.equal(log.some(call=>call.path.startsWith('/references/text')),false);assert.match(host.textContent,/The proposed law/);view.destroy();
});

test('owner-issued fetch failures retain the reference and retry exact candidate before explicit inspection',async()=>{
 const host=dom(),log=[],base=fakeRequest(log);let acquired=false,fail=true;
 const request=async(path,payload)=>{if(path.startsWith('/references/source'))return {available:acquired,kind:acquired?'text':null,acquisition_state:acquired?'ACQUIRED_UNREAD':'METADATA_ONLY',fulltext_candidates:[{id:'FETCH-owner',url:'https://example.org/source.txt'}]};if(path==='/references/fetch'){log.push({path,payload});if(fail)throw Error('Full-text retrieval failed (HTTP 403)');acquired=true;return {ok:true};}if(path.startsWith('/references/text')){log.push({path,payload});return {source_state:'extracted',text:'Inspected source passage.',reading_receipt:{id:'READ-exact',source_sha256:'sha256:source',locator:'characters0–25'}};}return base(path,payload);};
 const view=mountLiterature(host,{project:'paper',request});await view.ready;await find(host,'Read source').onclick();await find(host,'Fetch this full-text candidate').onclick();assert.match(host.textContent,/HTTP 403/);assert.ok(find(host,'Fetch this full-text candidate'));assert.equal(log.some(call=>call.path==='/references/literature-import'),false);
 fail=false;await find(host,'Fetch this full-text candidate').onclick();assert.equal(log.filter(call=>call.path.startsWith('/references/text')).length,0);assert.match(host.textContent,/ACQUIRED_UNREAD/);await find(host,'Read text').onclick();assert.match(host.textContent,/Inspected source passage/);assert.deepEqual(log.filter(call=>call.path==='/references/fetch').at(-1).payload,{project:'paper',key:row.key,candidate_id:'FETCH-owner'});view.destroy();
});

test('content search is a bounded registered-source read and does not pretend metadata is fulltext',async()=>{
 const host=dom(),log=[],base=fakeRequest(log);const request=async(path,payload)=>{if(path.startsWith('/references/source'))return {available:true,kind:'pdf'};if(path.startsWith('/references/text')){log.push({path,payload});return {source_state:'extracted',text:'Actual matching source content.',hit:{locator:'characters120–140'},reading_receipt:{id:'READ-search',source_sha256:'sha256:read-source'},query_next_offset:null};}return base(path,payload);};const view=mountLiterature(host,{project:'paper',request});await view.ready;await find(host,'Read source').onclick();const term=host.all().find(node=>node.name==='source_query');term.value='Actual';const form=term.parent.parent;await form.onsubmit({preventDefault(){}});assert.ok(log.at(-1).path.includes('query=Actual'));assert.match(host.textContent,/characters120–140/);assert.match(host.textContent,/Actual matching source content/);view.destroy();
});

test('meaning conflict retains authored rationale and source passage; only explicit inspected revision adoption changes guard',async()=>{
 const host=dom(),log=[],base=fakeRequest(log);let revision='sha256:original',fail=true;const request=async(path,payload)=>{if(path.startsWith('/concepts/state'))return {focus:{id:'claim:law',kind:'result',summary:'Inspected meaning '+revision},source_support:{meaning_revision:revision}};if(path.startsWith('/references/text'))return {source_state:'extracted',text:'Exact source passage.',reading_receipt:{id:'READ-source',locator:'source line2'}};if(path==='/references/literature-bind'){log.push({path,payload});if(fail)throw Error('The claim meaning changed');return {ok:true};}return base(path,payload);};const view=mountLiterature(host,{project:'paper',request,target:{claim_id:'claim:law',label:'Law'}});await view.ready;await find(host,'Link / review for this claim').onclick();await find(host,'Read source passage here').onclick();const dialog=host.all().find(node=>node.tag==='dialog'),form=dialog.all().find(node=>node.tag==='form'),rationale=form.all().find(node=>node.name==='rationale');rationale.value='Exact retained rationale';form.all().find(node=>node.name==='reading_status').value='partial';revision='sha256:changed';await form.onsubmit({preventDefault(){}});assert.equal(dialog.open,true);assert.equal(rationale.value,'Exact retained rationale');assert.equal(log.filter(call=>call.path==='/references/literature-bind').at(-1).payload.claim_revision,'sha256:original');
 await find(host,'Inspect current claim meaning').onclick();await form.onsubmit({preventDefault(){}});assert.equal(log.filter(call=>call.path==='/references/literature-bind').at(-1).payload.claim_revision,'sha256:original');await find(host,'Use this inspected claim revision').onclick();fail=false;await form.onsubmit({preventDefault(){}});assert.equal(log.filter(call=>call.path==='/references/literature-bind').at(-1).payload.claim_revision,'sha256:changed');assert.equal(log.filter(call=>call.path==='/references/literature-bind').at(-1).payload.reading_id,'READ-source');view.destroy();
});

test('bibliography pending disables citation placement and coverage is lazy, scoped and explicit',async()=>{
 const host=dom(),log=[],pending={...row,bibliography_state:'PENDING',bibliography:{state:'PENDING',entry_present:false,reason:'No bibliography consumer'}};const base=fakeRequest(log,[pending]);const request=async(path,payload)=>{if(path.startsWith('/references/literature-scope')){log.push({path,payload});return {revision:'sha256:scope',claims:[],pagination:{total:0,next_offset:null},gaps:[{kind:'citation-not-rendered'}],bibliography:{current:false,reason:'Build missing'},ready_for_completion:false};}return base(path,payload);};const view=mountLiterature(host,{project:'paper',request,target:{claim_id:'claim:law',label:'Law'},onInsertCitation(){throw Error('Pending insertion must not be offered');}});await view.ready;assert.equal(find(host,'Insert citation…'),undefined);assert.match(host.textContent,/Bibliography pending/);assert.equal(log.some(call=>call.path.includes('literature-scope')),false);assert.equal(log.some(call=>call.path.includes('/concepts/plan')),false);await find(host,'Inspect this claim coverage').onclick();assert.ok(log.at(-1).path.includes('node=claim%3Alaw'));assert.match(host.textContent,/citation-not-rendered/);assert.match(host.textContent,/not current/);view.destroy();
});

for(const operation of ['import','update'])test(`acknowledged reference ${operation} survives failed follow-up read without a second write`,async()=>{
 const {fixtures}=await import('./helpers/source_effect_fixture.mjs');
 const host=dom(),log=[],statuses=[],base=fakeRequest(log,[{...row,state:'STALE'}]);let saved=false,writes=0;
 const request=async(path,payload)=>{
  if(path==='/references/literature-import'||path==='/references/update'){
   writes++;saved=true;return {...fixtures.committed.result,association:row};
  }
  if(saved&&path.startsWith('/references/literature-uses'))throw Error('controlled library refresh unavailable');
  return base(path,payload);
 };
 const view=mountLiterature(host,{project:'book',request,status:(message)=>statuses.push(message)});await view.ready;
 if(operation==='update')await find(host,'Update source metadata').onclick();
 else{
  await find(host,'Discover sources').onclick();
  const doi=host.all().find(node=>node.name==='doi');doi.value='10.1234/source';
  await doi.parent.parent.onsubmit({preventDefault(){}});
 }
 assert.equal(writes,1);
 assert.match(statuses.at(-1),/Source saved.*Follow-up view refresh.*Do not repeat/);
 assert.doesNotMatch(statuses.at(-1),/save failed/i);
 view.destroy();
});

test('reference success keeps owner optional-maintenance warning after refresh',async()=>{
 const {fixtures}=await import('./helpers/source_effect_fixture.mjs');
 const host=dom(),log=[],statuses=[],base=fakeRequest(log,[{...row,state:'STALE'}]);
 const request=async(path,payload)=>path==='/references/update'?{...fixtures.optional.result,association:row}:base(path,payload);
 const view=mountLiterature(host,{project:'book',request,status:message=>statuses.push(message)});await view.ready;
 await find(host,'Update source metadata').onclick();
 assert.match(statuses.at(-1),/Source saved.*maintenance.*unavailable/);
 view.destroy();
});
