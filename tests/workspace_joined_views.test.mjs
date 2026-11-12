import {beforeEach,test} from 'node:test';
import assert from 'node:assert/strict';
import {mountStorage,openSavedTurn} from '../src/laplace/web/static_shared/workspace-material.mjs';
class Node{
 constructor(tag='div'){this.tag=tag;this.children=[];this.attrs={};this.dataset={};this.className='';this._text='';this.value='';this.isConnected=true;this.hidden=false;this.checked=false;this.disabled=false;}
 set textContent(v){this._text=String(v??'');this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent||'').join('');}
 append(...nodes){for(const node of nodes){node.parentElement=this;this.children.push(node);}}prepend(...nodes){for(const node of nodes)node.parentElement=this;this.children.unshift(...nodes);}replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}setAttribute(k,v){this.attrs[k]=v;}all(){return [this,...this.children.flatMap(n=>n.all?.()||[])];}querySelector(tag){return this.all().find(n=>n!==this&&n.tag===tag);}focus(){document.activeElement=this;}showModal(){this.open=true;}close(){this.open=false;this.onclose?.();}remove(){this.isConnected=false;if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(n=>n!==this);}
}
beforeEach(()=>{globalThis.document={createElement:tag=>new Node(tag),createTextNode:text=>{const n=new Node('#text');n.textContent=text;return n;},body:new Node('body')};});
const button=(host,label)=>host.all().find(n=>n.tag==='button'&&n.textContent===label);
const census=available=>({project:'fixture',measured_at:'2026-10-06T17:00:00Z',bytes:{conversation:50,own_files:1024,saved_versions:20},saved_versions_in_own_files:true,limitations:'Logical bytes; protected data retained.',cleanup:{available,empty_orphans:1,nonempty_orphans:2,active_orphans:0,scope:'empty orphan folders across this runtime',unavailable_reason:available?null:'Current-user process cwd/identity is unknown',unknown_process_ids:available?[]:[42],protected:['source','saved versions','saved bodies']}});
test('Storage is on demand and owner-unavailable cleanup cannot be confirmed or requested',async()=>{
 const calls=[],host=new Node(),controller=mountStorage(host,{project:'fixture',request:async(path,payload)=>{calls.push({path,payload});return census(false);}});assert.equal(calls.length,0);controller.panel.open=true;await controller.panel.ontoggle();assert.equal(calls.length,1);assert.match(host.textContent,/cwd\/identity is unknown/);assert.match(host.textContent,/saved bodies/);assert.equal(button(host,'Remove empty unused session folders').disabled,true);assert.equal(host.all().find(n=>n.tag==='input').disabled,true);await button(host,'Remove empty unused session folders').onclick();assert.equal(calls.length,1);
});
test('Only available reviewed empty-folder scope can post confirmed cleanup, then remeasures',async()=>{
 const calls=[],host=new Node(),controller=mountStorage(host,{project:'fixture',request:async(path,payload)=>{calls.push({path,payload});return payload?{removed:['unused'],act_id:'ACT-owned'}:census(true);}});controller.panel.open=true;await controller.panel.ontoggle();const remove=button(host,'Remove empty unused session folders'),confirm=host.all().find(n=>n.tag==='input');assert.equal(remove.disabled,true);await remove.onclick();assert.equal(calls.length,1);confirm.checked=true;confirm.onchange();assert.equal(remove.disabled,false);await remove.onclick();assert.deepEqual(calls[1],{path:'/work/storage/prune',payload:{project:'fixture',confirm:true}});assert.equal(calls[2].path,'/work/storage?project=fixture');assert.match(host.textContent,/1 empty session folders removed/);
});
test('Saved turn is a human reader; request/reply and exact controls/actions pages stay owner-backed and lazy',async()=>{
 const calls=[],summary={id:'WT-one',session_id:'WS-one',text:'Check this result',reply:{display_text:'The saved result is conditional.',status:'completed'},action_count:1,failure_count:0};const dialog=await openSavedTurn({project:'fixture',turnId:'WT-one',request:async path=>{calls.push(path);const q=new URL(path,'http://test').searchParams;return q.get('view')==='summary'?{project:'fixture',turn:summary,exact:true}:{project:'fixture',turn_id:q.get('id'),view:q.get('view'),items:[{operation:'store_artifact',outcome:{status:'SUCCEEDED',summary:'Saved exact note'}}],pagination:{total:1,next_offset:null}};},renderMarkdown:async(host,text)=>{host.textContent=text;}});assert.equal(calls.length,1);assert.match(dialog.textContent,/Original request/);assert.match(dialog.textContent,/saved result is conditional/);assert.ok(dialog.textContent.indexOf('saved result is conditional')<dialog.textContent.indexOf('Original request'),'the saved result precedes the lazily read request');assert.ok(button(dialog,'Open this conversation'));assert.ok(dialog.all().some(n=>n.tag==='a'&&n.download==='saved-turn.json'));const changes=dialog.all().find(n=>n.tag==='details'&&n.children[0].textContent.startsWith('Saved project changes'));changes.open=true;await changes.ontoggle();assert.equal(calls.length,2);assert.match(calls[1],/view=actions/);assert.match(dialog.textContent,/Saved exact note/);dialog.close();assert.equal(dialog.isConnected,false);
});
test('Saved work basis preserves consumed revisions and opens the current parent explicitly',async()=>{
 const opened=[],turn={id:'WT-basis',session_id:'WS-basis',text:'Trace selected work',work_id:'WORK-child',work_basis:{revision:'sha256:consumed-child',ancestors:[{id:'WORK-parent',revision:'sha256:consumed-parent'}]}};
 const dialog=await openSavedTurn({project:'fixture',turnId:turn.id,request:async()=>({project:'fixture',turn}),onWork:async id=>opened.push(id)});
 assert.match(dialog.textContent,/Consumed work revision: sha256:consumed-child/);
 assert.match(dialog.textContent,/WORK-parent · sha256:consumed-parent/);
 await button(dialog,'Open current work').onclick();
 assert.deepEqual(opened,['WORK-parent']);assert.equal(dialog.isConnected,false);
});


test('Saved failures unwrap canonical records and retain later-success evidence',async()=>{
 const turn={id:'WT-failures',session_id:'WS-failures',text:'Inspect source failures',failure_count:2};
 const dialog=await openSavedTurn({project:'fixture',turnId:turn.id,request:async path=>new URL(path,'http://test').searchParams.get('view')==='summary'?{project:'fixture',turn}:{project:'fixture',turn_id:turn.id,view:'failures',items:[
  {origin:'tool-failure',record:{operation:'reference_fetch',error:'A full text URL is required.',payload:{key:'source-one'}},resolved_later:true},
  {origin:'tool-failure',record:{operation:'source',error:'Selected source is unavailable.'},resolved_later:false}
 ],pagination:{total:2,next_offset:null}}});
 const failures=dialog.all().find(n=>n.tag==='details'&&n.children[0].textContent.startsWith('Recorded failed attempts'));
 failures.open=true;await failures.ontoggle();
 assert.match(dialog.textContent,/reference fetch/);assert.match(dialog.textContent,/A full text URL is required/);assert.match(dialog.textContent,/source-one/);
 assert.match(dialog.textContent,/later matching attempt succeeded/);assert.match(dialog.textContent,/No matching successful retry/);
 assert.match(dialog.textContent,/Selected source is unavailable/);dialog.close();
});

test('saved child opens exact parent and dispatch, while focused failures actually read owner records',async()=>{
 const calls=[],works=[],child={id:'WT-child',session_id:'WS-child',text:'Judge returns',dispatch_id:'WORK-dispatch',parent_turn_id:'WT-parent',failure_count:1};
 const request=async path=>{calls.push(path);const q=new URL(path,'http://test').searchParams;return q.get('view')==='summary'?{project:'fixture',turn:q.get('id')==='WT-parent'?{id:'WT-parent',session_id:'WS-parent',text:'Launch exact children'}:child}:{project:'fixture',turn_id:q.get('id'),view:q.get('view'),items:[{record:{id:'FAIL-one',operation:'source',error:'Basis changed'}}],pagination:{next_offset:null,total:1}};};
 const dialog=await openSavedTurn({project:'fixture',turnId:child.id,request,onWork:id=>works.push(id),focusView:'failures'});
 assert.ok(calls.some(path=>path.includes('view=failures')));assert.match(dialog.textContent,/Basis changed/);
 await button(dialog,'Open dispatch work').onclick();assert.deepEqual(works,['WORK-dispatch']);
 const fresh=await openSavedTurn({project:'fixture',turnId:child.id,request});await button(fresh,'Read exact parent turn').onclick();assert.ok(calls.at(-1).includes('id=WT-parent'));assert.equal(document.body.all().filter(n=>n.tag==='dialog').length,1);
 // The parent's identity leads; its original request text is one deliberate read behind the result.
 assert.match(document.body.textContent,/Turn: WT-parent/);assert.ok(!document.body.textContent.includes('Launch exact children'));
 const parent=document.body.all().find(n=>n.tag==='dialog');await button(parent,'Original request').onclick();assert.match(document.body.textContent,/Launch exact children/);
});


test('failure inspector shows exact retained guidance and distinguishes absent historical guidance',async()=>{
 const returned={ok:false,next_reads:[{operation:'source',payload:{files:['exact.tex'],line_start:9}}],consumed_read_recovery:{consumed_revision:'old',observed_revision:'at-failure'}};
 const turn={id:'WT-recovery',session_id:'WS-r',text:'Inspect failures',failure_count:2};
 const dialog=await openSavedTurn({project:'fixture',turnId:turn.id,focusView:'failures',request:async path=>new URL(path,'http://t').searchParams.get('view')==='summary'?{project:'fixture',turn}:{project:'fixture',turn_id:turn.id,view:'failures',items:[{record:{operation:'source',error:'Stale read',recovery:returned}},{record:{operation:'source',error:'Old failure'}}],pagination:{total:2,next_offset:null}}});
 const saved=dialog.all().find(n=>n.tag==='details'&&n.children[0].textContent==='Exact saved returned guidance');saved.open=true;saved.ontoggle();
 assert.match(dialog.textContent,/at-failure/);assert.match(dialog.textContent,/exact.tex/);assert.match(dialog.textContent,/unavailable in this saved record/);
});

test('exact saved turn offers owner result beside original invalid link and retains scope/pin on action inspection',async()=>{
 const opened=[],pin='d'.repeat(64),url='/research/artifact?'+new URLSearchParams({project:'fixture',scope:'manuscript',path:'result notes/note.txt',expected_sha256:pin,artifact_id:'ART-saved'}),read={project:'fixture',path:'result notes/note.txt',scope:'manuscript',expected_sha256:pin,artifact_id:'ART-saved',url};
 const original='[result](/invented/provider/cwd/result notes/note.txt)',turn={id:'WT-results',session_id:'WS-results',text:'Read result',reply:{text:original},result_links:[read],action_count:1};
 const dialog=await openSavedTurn({project:'fixture',turnId:turn.id,onOpenArtifact:(...args)=>opened.push(args),focusView:'actions',request:async path=>new URL(path,'http://t').searchParams.get('view')==='summary'?{project:'fixture',turn}:{project:'fixture',turn_id:turn.id,view:'actions',items:[{operation:'store_artifact',outcome:{human_read:read}}],pagination:{total:1,next_offset:null}}});
 assert.ok(dialog.textContent.includes(original));const links=dialog.all().filter(n=>n.tag==='a'&&n.href===url);assert.equal(links.length,2);await links[0].onclick({preventDefault(){}});await links[1].onclick({preventDefault(){}});
 assert.ok(opened.every(args=>args[0]==='result notes/note.txt'&&args[2].scope==='manuscript'&&args[2].expectedSha256===pin&&args[2].artifactId==='ART-saved'));
});
