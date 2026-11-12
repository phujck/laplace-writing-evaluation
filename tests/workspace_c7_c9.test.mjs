// M5 C7-C9 (2026-10-14): the manuscript band and passage menu, the proposal step header, the
// conversation row facets and artifact rows, the Material readers and file chips, and the asset
// registry entry for the typed topology module.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {installDOM,Node} from './helpers/evidence_reader_harness.mjs';
import {WorkspaceSession} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {mountMaterial} from '../src/laplace/web/static_shared/workspace-material.mjs';
import {walkSource} from './helpers/walk_source.mjs';
const src=name=>readFileSync(new URL('../src/laplace/'+name,import.meta.url),'utf8');

test('the passage menu groups its items under Edit, Insert, Structure and Ask and no longer carries Undo/Redo',()=>{
 const panel=src('static_shared/writing-panel.mjs');
 assert.ok(!/item\('Undo/.test(panel)&&!/item\('Redo/.test(panel),'Undo/Redo left the menu (they are in the editor band and on the keys)');
 assert.match(panel,/const groups=\{edit:\[\],insert:\[\],structure:\[\],ask:\[\]\}/);assert.match(panel,/\['Edit',groups\.edit\],\['Insert',groups\.insert\],\['Structure',groups\.structure\],\[askTitle,groups\.ask\]/);
 // the Ask title is 'Ask' unless the menu is the bounded unavailable/loading disposition (S2 L-MENU-ELIGIBILITY)
 assert.match(panel,/let askTitle='Ask';/);
 assert.match(panel,/item\('Open in TeX'/);assert.ok(!/item\('Edit document source'/.test(panel));
 const walk=walkSource();assert.match(walk,/proposal-head/);assert.match(walk,/proposalStepHeading\(data,edit\.edit_id/);
 assert.match(walk,/M5 C7 adds redoEdit beside undoEdit to the shell's set/);
 const css=src('static_shared/workspace.css');assert.ok(!/data-view="manuscript"\]\{--nav-width/.test(css),'no nav widening on Manuscript');
 const registry=src('shared_ui.py');assert.match(registry,/"workspace-topology\.mjs": "text\/javascript; charset=utf-8"/);
});

test('a thread row carries its facets as chips and its saved artifacts as relation rows, from the owner row alone',()=>{
 const dom=installDOM();try{
  const opened=[];const current={project:'p',onApplication(){},guard:fn=>fn(),onOpenArtifact:(...args)=>opened.push(args),status(){},authorMessage(){},actions(){},failures(){},remoteHistory(){},
   message:()=>{const row=new Node('article');row.dataset={};dom.body.append(row);return row;},onReadTurn:null,parentContinuationValue:null};
  current.facets=WorkspaceSession.prototype.facets;current.proposal=WorkspaceSession.prototype.proposal;current.appendTurn=WorkspaceSession.prototype.appendTurn;
  const turn={id:'turn-1',text:'Request',action_count:2,failure_count:1,reply:{text:'Done',status:'completed'},
   result_links:[{url:'/research/artifact?'+new URLSearchParams({project:'p',path:'notes/a.md',scope:'project',artifact_id:'ART-'+'a'.repeat(32),expected_sha256:'b'.repeat(64)}),path:'notes/a.md',artifact_id:'ART-'+'a'.repeat(32),expected_sha256:'b'.repeat(64)}]};
  current.appendTurn(turn,false);
  const row=dom.body.children.at(-1);const chips=row.all().find(n=>n.attrs['data-control']==='conversation:turn');assert.ok(chips,'facet chips are declared');
  assert.match(chips.textContent,/2 saved changes/);assert.match(chips.textContent,/1 failed attempt/);assert.equal(row.children[0],chips,'facets lead the row');
  const artifacts=row.all().find(n=>n.attrs['data-control']==='conversation:artifact');assert.ok(artifacts);
  const door=artifacts.all().find(n=>n.tag==='button');assert.equal(door.textContent,'notes/a.md');assert.match(artifacts.textContent,/receipt aaaaaaaaaaaa/);
  const bare=new Node('article');WorkspaceSession.prototype.facets.call(current,bare,[]);assert.equal(bare.children.length,0,'no facets, no chip row');
 }finally{dom.restore();}
});

test('Material lists readers as relation rows and recorded files with an availability chip and Read as the primary action',async()=>{
 const dom=installDOM();try{
  const host=new Node('main'),shown=[],opened=[];dom.body.append(host);
  const info={capabilities:{manuscript:true,research:true,review:false,presentation:true,materials:true,material_references:false}};
  const request=async path=>{if(path.startsWith('/work/materials'))return {materials:[{id:'m1',path:'notes/present.md',scope:'project',availability:'present',recorded_revision:'sha256:'+'1'.repeat(64)},{id:'m2',path:'notes/gone.md',scope:'project',availability:'missing'}],pagination:{next_offset:null,total:2},coverage:'Two recorded files.'};throw Error('unexpected '+path);};
  await mountMaterial(host,{project:'p',info,request,onShow:view=>shown.push(view),onArtifact:(...args)=>opened.push(args),onHistory(){},projects:[]});
  const readers=host.all().find(n=>n.attrs['data-control']==='material:reader');assert.ok(readers);
  const doors=readers.all().filter(n=>n.tag==='button').map(n=>n.textContent);assert.deepEqual(doors,['Manuscript','Research & sources','Figures & output'],'only available readers are doors');
  await readers.all().find(n=>n.tag==='button').onclick();assert.deepEqual(shown,['manuscript']);
  const files=host.all().filter(n=>n.attrs['data-control']==='material:file');assert.equal(files.length,2);
  assert.match(files[0].textContent,/Recorded/);assert.match(files[1].textContent,/Missing/);
  const read=files[0].all().find(n=>n.tag==='button'&&n.textContent.startsWith('Read '));assert.ok(read.className.includes('primary'));
  assert.equal(files[1].all().find(n=>n.tag==='button'&&n.textContent.startsWith('Read ')),undefined,'a missing file offers no read');
 }finally{dom.restore();}
});

// C7-C9 repair H2/H3/H4 (2026-10-14)
import {createManuscriptRefresh,proposalStepHeading,selectedProposalBody,manuscriptDocumentVersion} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {groupedMenu} from '../src/laplace/web/static_shared/workspace-presentation.mjs';

test('H3: a grouped menu focuses its first enabled menuitem, never a group heading, and skips disabled items',()=>{
 const dom=installDOM();try{
  const button=(text,disabled=false)=>{const b=new Node('button');b.textContent=text;b.disabled=disabled;b.setAttribute('role','menuitem');return b;};
  const menu=new Node('div');
  const first=groupedMenu(menu,[['Edit',[]],['Insert',[button('Insert reference…',true),button('Italic')]],['Ask',[button('Discuss this passage')]]]);
  assert.equal(menu.children[0].attrs.role,'presentation');assert.equal(menu.children[0].textContent,'Insert','the first child is the heading of the first non-empty group');
  assert.ok(first&&first.tag==='button'&&first.textContent==='Italic','the first ENABLED menuitem is the focus target');
  let active=null;first.focus=()=>{active=first.textContent;};first.focus();assert.equal(active,'Italic');
  assert.equal(groupedMenu(new Node('div'),[['Edit',[]]]),null);
  const panel=src('static_shared/writing-panel.mjs');assert.match(panel,/const firstItem=flush\(\);/);assert.match(panel,/firstItem\?\.focus\(\);/);assert.ok(!/menu\.firstElementChild\?\.focus\(\)/.test(panel));
 }finally{dom.restore();}
});

test('H4: the proposal step heading follows the owner navigation scope and the selected exact edit, not the loaded bodies',()=>{
 const summary={turn_id:'WT-synthetic',proposal_version:'sha256:synthetic',edits:[{edit_id:'a',status:'pending',file:'paper/a.tex'},{edit_id:'b',status:'pending',file:'paper/body.tex'}]};
 const body={turn_id:summary.turn_id,proposal_version:summary.proposal_version,edits:[{edit_id:'b',status:'pending',file:'paper/body.tex'}]};
 const data=selectedProposalBody(summary,body,'b');
 assert.equal(data.edits.length,1);assert.equal(data.navigation_edits.length,2);
 const second=proposalStepHeading(data,'b',{file:'paper/body.tex'});
 assert.equal(second.eyebrow,'Review change 2 of 2 · body.tex');assert.equal(second.scope,'candidate');assert.equal(second.loaded,1);assert.equal(second.total,2);
 const first=proposalStepHeading(data,'a',{conflict:true,file:'paper/a.tex'});assert.equal(first.eyebrow,'Compare change 1 of 2 · a.tex');assert.equal(first.chip,'Needs comparison');
 // a terminal (applied) edit still counts in the owner scope; the remaining note names the pending ones
 const terminal={...data,navigation_edits:[{edit_id:'a',status:'applied'},{edit_id:'b',status:'pending'},{edit_id:'c',status:'pending'}]};
 const mid=proposalStepHeading(terminal,'b',{});assert.equal(mid.eyebrow,'Review change 2 of 3');assert.equal(mid.remaining,2);assert.match(mid.note,/2 awaiting review/);
 // no owner scope: the heading says what is loaded and asserts no candidate count
 const loadedOnly=proposalStepHeading({edits:[{edit_id:'x',status:'pending'},{edit_id:'y',status:'conflict'}]},'y',{});
 assert.equal(loadedOnly.eyebrow,'Review change 2 of 2 loaded');assert.equal(loadedOnly.scope,'loaded');assert.equal(loadedOnly.remaining,null);
 const walk=walkSource();assert.match(walk,/proposalStepHeading\(data,edit\.edit_id,\{conflict,unproven,file:range\.file\}\)/);assert.ok(!/stepIndex=pending\.findIndex/.test(walk));
});

test('H2: a compact unchanged answer is the token only; the refresh loop accepts it without a source revision or a body read',async()=>{
 const current={project:'book',current_revision:'owner:one',presentation_revision:'presentation:one',sections:[{id:'s',blocks:[]}],source_observation:{schema_version:'laplace.manuscript-source-observation/1',revision:'source:one',source_revision:'root',file_revisions:{'main.tex':'one'}}};
 let heads=0,bodies=0,observed=[];
 const walk={ready:()=>true,documentVersion:()=>manuscriptDocumentVersion(current),sourceObservation:()=>current,editState:()=>({}),refresh:async()=>{throw Error('unchanged must not repaint');}};
 const control=createManuscriptRefresh({project:'book',observe:async()=>{heads++;return {project:'book',unchanged:true,summary_revision:'sha256:'+'a'.repeat(64),document_status:'READY',as_of:'now'};},read:async()=>{bodies++;throw Error('unchanged must not read the body');},getWalk:()=>walk,visible:()=>true,onObservation:value=>observed.push(value),status:()=>{}});
 try{const result=await control.check();assert.equal(result.checked,true);assert.equal(result.changed,false);assert.equal(result.unchanged,true);assert.equal(heads,1);assert.equal(bodies,0);assert.equal(observed[0].summary_revision,'sha256:'+'a'.repeat(64));
  const bytes=Buffer.byteLength(JSON.stringify({project:'writing-system-architecture',unchanged:true,summary_revision:'sha256:'+'a'.repeat(64),document_status:'READY',as_of:'2026-10-14T07:00:00.000000+00:00'}));assert.ok(bytes<=300,'the unchanged answer shape stays under 300 B ('+bytes+')');
  // a foreign project's unchanged answer is still refused
  const foreign=createManuscriptRefresh({project:'book',observe:async()=>({project:'other',unchanged:true,summary_revision:'sha256:'+'b'.repeat(64)}),read:async()=>{throw Error('no');},getWalk:()=>walk,visible:()=>true,status:()=>{}});
  const refused=await foreign.check();assert.equal(refused.checked,false);assert.match(refused.error,/incompatible/);foreign.destroy();
 }finally{control.destroy();}
});

test('H1: the pane renders a compact row (counts, excerpts, no links) and loads the artifact rows on request from the single-turn summary',async()=>{
 const dom=installDOM();try{
  const opened=[],reads=[];const prior=globalThis.fetch;
  globalThis.fetch=async(path)=>{reads.push(path);return {ok:true,status:200,headers:{get:()=>'application/json'},json:async()=>({project:'p',turn:{id:'turn-1',result_links:[{url:'/research/artifact?'+new URLSearchParams({project:'p',path:'notes/a.md',scope:'project',artifact_id:'ART-'+'a'.repeat(32),expected_sha256:'b'.repeat(64)}),path:'notes/a.md',artifact_id:'ART-'+'a'.repeat(32),expected_sha256:'b'.repeat(64)}]}})};};
  const current={project:'p',onApplication(){},guard:fn=>fn(),onOpenArtifact:(...args)=>opened.push(args),status(){},authorMessage(){},actions(){},failures(){},remoteHistory(){},
   message:()=>{const row=new Node('article');row.dataset={};dom.body.append(row);return row;},onReadTurn:null,parentContinuationValue:null,find:()=>new Node('div')};
  current.facets=WorkspaceSession.prototype.facets;current.proposal=WorkspaceSession.prototype.proposal;current.appendTurn=WorkspaceSession.prototype.appendTurn;
  current.appendTurn({id:'turn-1',text:'Request excerpt',text_chars:5000,text_truncated:true,action_count:6,result_links_total:1,detail:{turn_id:'turn-1'},reply:{id:'r',status:'completed',display_text:'Done excerpt',display_text_chars:7000,display_text_truncated:true}},false);
  const row=dom.body.children.at(-1);const artifacts=row.all().find(n=>n.attrs['data-control']==='conversation:artifact');assert.ok(artifacts);assert.equal(artifacts.tag,'details');
  assert.match(artifacts.textContent,/1 saved artifact from this turn/);assert.equal(reads.length,0,'nothing is read for a closed row');
  artifacts.open=true;await artifacts.ontoggle();await new Promise(r=>setTimeout(r,0));
  assert.equal(reads.length,1);assert.match(reads[0],/\/authoring\/session-turn\?project=p&id=turn-1&view=summary/);
  const door=artifacts.all().find(n=>n.tag==='button');assert.equal(door.textContent,'notes/a.md');
  globalThis.fetch=prior;
 }finally{dom.restore();}
});

// C7-C9 repair2 R2-R5 (2026-10-14)
import {contextUsageCounter,meterMatchesSelection} from '../src/laplace/web/static_shared/workspace-session.mjs';

test('R2: the audit basis never reports omitted words as zero, the row meter keeps its identity and a historical meter is not matched to next settings',()=>{
 const dom=installDOM();try{
  const detail=new Node('section'),origin=new Node('div');
  const audit=Object.create(WorkspaceSession.prototype);Object.assign(audit,{project:'synthetic',session:'WS-synthetic',selectedTurnRecord:{id:'WT-synthetic',mode:'work',selection:{files:['paper/body.tex'],line_start:3,line_end:9,quote_chars:3000},unsaved_draft:{status:'UNSAVED',format:'tex',text_chars:5000,text_truncated:true,reason:'synthetic',text_omitted:true},detail:{turn_id:'WT-synthetic'}},find:q=>q==='[data-origin]'?origin:q==='[data-context-inspection]'?detail:null,authoredContext:()=>({}),origin:{},sessionRows:[]});
  audit.paintContext({});const disclosure=detail.all().find(x=>x.tag==='details');disclosure.open=true;disclosure.ontoggle();const recorded=JSON.parse(detail.all().find(x=>x.tag==='pre').textContent);
  assert.equal(recorded.selection.quote_chars,3000);assert.equal(recorded.selection.unsaved_draft_chars,5000);assert.match(recorded.work_basis,/uninspected/);
  const bare=Object.create(WorkspaceSession.prototype);Object.assign(bare,{project:'p',session:'s',selectedTurnRecord:{id:'t',selection:{files:['a.tex']},unsaved_draft:{status:'UNSAVED'},detail:{turn_id:'t'}},find:q=>q==='[data-origin]'?origin:q==='[data-context-inspection]'?detail:null,authoredContext:()=>({}),origin:{},sessionRows:[]});
  detail.replaceChildren();bare.paintContext({});const d2=detail.all().find(x=>x.tag==='details');d2.open=true;d2.ontoggle();const r2=JSON.parse(detail.all().find(x=>x.tag==='pre').textContent);
  assert.equal(r2.selection.quote_chars,0,'no quote at all is zero');assert.match(r2.selection.unsaved_draft_chars,/uninspected/,'a draft without a length marker is uninspected, not zero');
  const reply={id:'WR-19',status:'completed',provider:'claude',model:'m',context_tokens_used:4321,context_window_effective:8000,usage:{input_tokens:1019,output_tokens:50},usage_facts_projection:{schema_version:'laplace.provider-usage-facts/1',selected:{context_snapshot:{metric:'last_request_input_proxy',value:1019}}}};
  const counter=contextUsageCounter(reply.usage,reply);assert.equal(counter.value,1019);assert.equal(counter.limit,8000);assert.equal(counter.kind,'request-proxy');
  assert.equal(meterMatchesSelection(reply,'codex','next-model',true),false,'a historical Claude meter never matches proposed Codex settings');
  assert.equal(meterMatchesSelection(reply,'claude','m',true),true);assert.equal(meterMatchesSelection({},'codex','next-model',true),false,'a meter without identity is unknown, not compatible');
  assert.equal(meterMatchesSelection({},'codex','next-model',false),true,'the active turn and the session keep the permissive rule');
 }finally{dom.restore();}
});

test('R3/R4: the artifact disclosure states a lower bound, loads only after an exact successful read, retries after a failure, refuses a wrong owner and reads nothing while closed',async()=>{
 const dom=installDOM();try{
  const priorFetch=globalThis.fetch,priorWindow=globalThis.window;globalThis.window={dispatchEvent(){},addEventListener(){},removeEventListener(){}};
  let requests=0,mode='fail';const links=n=>Array.from({length:n},(_,i)=>({url:'/research/artifact?'+new URLSearchParams({project:'p',path:'notes/a'+i+'.md',scope:'project',artifact_id:'ART-'+String(i).padStart(32,'0'),expected_sha256:'b'.repeat(64)}),path:'notes/a'+i+'.md',artifact_id:'ART-'+String(i).padStart(32,'0'),expected_sha256:'b'.repeat(64)}));
  globalThis.fetch=async()=>{requests++;if(mode==='fail')throw Error('synthetic network failure');const turn=mode==='wrong'?{id:'other',result_links:links(1)}:{id:'turn-1',result_links:links(20),result_links_more:true,result_links_total_basis:'at-least',result_links_total:21};return {ok:true,status:200,headers:{get:()=>'application/json'},json:async()=>({project:'p',turn})};};
  const failures=[],reads=[];const current={project:'p',onApplication(){},guard:async fn=>{try{await fn();}catch(e){failures.push(e.message);}},onOpenArtifact(){},status(){},authorMessage(){},actions(){},failures(){},remoteHistory(){},message:()=>{const n=new Node('article');dom.body.append(n);return n;},onReadTurn:id=>{reads.push(id);},parentContinuationValue:null,find:()=>new Node('div')};
  current.facets=WorkspaceSession.prototype.facets;current.proposal=WorkspaceSession.prototype.proposal;
  WorkspaceSession.prototype.appendTurn.call(current,{id:'turn-1',text:'request',result_links_total:21,result_links_more:true,result_links_total_basis:'at-least',detail:{turn_id:'turn-1'},reply:{id:'r',status:'completed',display_text:'answer'}},false);
  const artifacts=dom.body.all().find(x=>x.attrs['data-control']==='conversation:artifact');
  assert.match(artifacts.children[0].textContent,/^At least 21 saved artifacts/);assert.equal(requests,0,'closed: no read');
  const tick=()=>new Promise(r=>setTimeout(r,0));
  artifacts.open=true;artifacts.ontoggle();await tick();assert.equal(requests,1);assert.match(artifacts.textContent,/Saved artifacts unavailable: /);assert.equal(failures.length,1);
  artifacts.open=false;artifacts.ontoggle();artifacts.open=true;artifacts.ontoggle();await tick();assert.equal(requests,2,'reopening after a failure reads again');
  mode='wrong';const retry=artifacts.all().find(n=>n.tag==='button'&&n.textContent==='Retry');assert.ok(retry);await retry.onclick();await tick();assert.equal(requests,3);assert.match(artifacts.textContent,/different project or turn/);
  mode='ok';await artifacts.all().find(n=>n.tag==='button'&&n.textContent==='Retry').onclick();await tick();assert.equal(requests,4);
  const doors=artifacts.all().filter(n=>n.tag==='button'&&n.textContent.startsWith('notes/'));assert.equal(doors.length,20,'twenty exact rows loaded');
  assert.match(artifacts.textContent,/Showing 20 of at least 21 saved artifacts; the saved turn's actions list the rest/);
  await artifacts.all().find(n=>n.tag==='button'&&n.textContent==='Read the saved turn').onclick();assert.deepEqual(reads,['turn-1']);
  artifacts.open=false;artifacts.ontoggle();artifacts.open=true;artifacts.ontoggle();await tick();assert.equal(requests,4,'loaded after success: no further read');
  globalThis.fetch=priorFetch;globalThis.window=priorWindow;
 }finally{dom.restore();}
});

test('R5: a token-only unchanged answer cannot settle a source change the reading view has not applied',async()=>{
 const doc=r=>({ok:true,project:'book',root:'main.tex',current_revision:'owner:'+r,source_revision:'source:'+r,presentation_revision:'presentation:one',sections:[{id:'s',blocks:[]}],source_observation:{schema_version:'laplace.manuscript-source-observation/1',revision:'source:'+r,source_revision:'root',file_revisions:{'main.tex':r}}});
 for(const failure of [false,true]){
  let current=doc('A'),dirty=!failure,heads=0,bodies=0,applied=0;const notices=[];
  const walk={ready:()=>true,documentVersion:()=>manuscriptDocumentVersion(current),sourceObservation:()=>current,editState:()=>({dirty}),refresh:async({document})=>{current=document;applied++;return true;}};
  const c=createManuscriptRefresh({project:'book',getWalk:()=>walk,visible:()=>true,observe:async()=>++heads===1?{...doc('B'),summary_revision:'sha256:'+'b'.repeat(64)}:{project:'book',unchanged:true,summary_revision:'sha256:'+'b'.repeat(64),document_status:'READY',as_of:'now'},read:async()=>{bodies++;if(failure&&bodies===1)throw Error('synthetic transient body read failure');return doc('B');},status:(m)=>notices.push(m)});
  const first=await c.check();assert.equal(first.deferred,failure?undefined:true);
  if(!failure){assert.equal(c.pending,true);dirty=false;const second=await c.settled();assert.equal(second.refreshed,true,'settle reads and applies the deferred target');}
  else{assert.equal(c.pending,true);assert.equal(current.current_revision,'owner:A');const second=await c.check();assert.equal(second.refreshed,true,'the token-only answer did not clear the failed target; the body was re-read');}
  assert.equal(current.current_revision,'owner:B');assert.equal(applied,1);assert.equal(c.pending,false);
  const third=await c.check();assert.equal(third.unchanged,true);assert.equal(third.changed,false);assert.equal(bodies,failure?2:1,'once reconciled, the idle shortcut reads no body');
  c.destroy();
 }
 // genuinely current: the shortcut stands from the start
 let bodies=0;const current=doc('A');const walk={ready:()=>true,documentVersion:()=>manuscriptDocumentVersion(current),sourceObservation:()=>current,editState:()=>({}),refresh:async()=>{throw Error('no');}};
 const idle=createManuscriptRefresh({project:'book',getWalk:()=>walk,visible:()=>true,observe:async()=>({project:'book',unchanged:true,summary_revision:'sha256:'+'a'.repeat(64),document_status:'READY',as_of:'now'}),read:async()=>{bodies++;throw Error('no');},status:()=>{}});
 const result=await idle.check();assert.equal(result.unchanged,true);assert.equal(bodies,0);idle.destroy();
});

// C7-C9 repair3 R3-current / R5-body-coordinates (2026-10-14)
test('R3: the artifact header and coverage follow the current exact response, not the entry snapshot',async()=>{
 const dom=installDOM();try{
  const priorFetch=globalThis.fetch,priorWindow=globalThis.window;globalThis.window={dispatchEvent(){},addEventListener(){},removeEventListener(){}};
  const links=n=>Array.from({length:n},(_,i)=>({url:'/research/artifact?'+new URLSearchParams({project:'p',path:'notes/a'+i+'.md',scope:'project',artifact_id:'ART-'+String(i).padStart(32,'0'),expected_sha256:'b'.repeat(64)}),path:'notes/a'+i+'.md',artifact_id:'ART-'+String(i).padStart(32,'0'),expected_sha256:'b'.repeat(64)}));
  const open=async(entry,current)=>{globalThis.fetch=async()=>({ok:true,status:200,headers:{get:()=>'application/json'},json:async()=>({project:'p',turn:{id:'turn-1',...current}})});
   const reads=[];const host={project:'p',onApplication(){},guard:async fn=>fn(),onOpenArtifact(){},status(){},authorMessage(){},actions(){},failures(){},remoteHistory(){},message:()=>{const n=new Node('article');dom.body.append(n);return n;},onReadTurn:id=>reads.push(id),parentContinuationValue:null,find:()=>new Node('div')};
   host.facets=WorkspaceSession.prototype.facets;host.proposal=WorkspaceSession.prototype.proposal;
   WorkspaceSession.prototype.appendTurn.call(host,{id:'turn-1',text:'request',...entry,detail:{turn_id:'turn-1'},reply:{id:'r',status:'completed',display_text:'answer'}},false);
   const artifacts=dom.body.all().filter(x=>x.attrs['data-control']==='conversation:artifact').at(-1);const before=artifacts.children[0].textContent;artifacts.open=true;artifacts.ontoggle();await new Promise(r=>setTimeout(r,0));
   return {before,header:artifacts.children[0].textContent,notes:artifacts.all().filter(x=>x.tag==='p').map(x=>x.textContent),rows:artifacts.all().filter(n=>n.tag==='button'&&n.textContent.startsWith('notes/')).length,reads};};
  // the turn gained actions between the entry row (6) and the lazy read (20 of at least 21)
  const grown=await open({result_links_total:6},{result_links:links(20),result_links_more:true,result_links_total_basis:'at-least',result_links_total:21});
  assert.equal(grown.before,'6 saved artifacts from this turn');assert.equal(grown.header,'At least 21 saved artifacts from this turn · 20 listed · the entry row counted 6');
  assert.ok(grown.notes.some(t=>t.startsWith('Showing 20 of at least 21 saved artifacts; the saved turn\'s actions list the rest.')));assert.equal(grown.rows,20);
  // the same without an owner total: the lazy response alone is the authority ("at least 20")
  const noTotal=await open({result_links_total:6},{result_links:links(20),result_links_more:true,result_links_total_basis:'at-least'});
  assert.equal(noTotal.header,'At least 20 saved artifacts from this turn · the entry row counted 6');assert.ok(noTotal.notes.some(t=>t.startsWith('Showing 20 of at least 20')));
  // a static exact turn: six on entry, six listed, no coverage sentence, no "entry" suffix
  const exact=await open({result_links_total:6},{result_links:links(6),result_links_more:false,result_links_total:6});
  assert.equal(exact.header,'6 saved artifacts from this turn');assert.ok(!exact.notes.some(t=>t.startsWith('Showing')));assert.equal(exact.rows,6);
  // a turn that lost nothing but whose entry counted the cap: 21 at least -> 20 listed of at least 21
  const capped=await open({result_links_total:21,result_links_more:true,result_links_total_basis:'at-least'},{result_links:links(20),result_links_more:true,result_links_total_basis:'at-least',result_links_total:21});
  assert.equal(capped.header,'At least 21 saved artifacts from this turn · 20 listed');
  globalThis.fetch=priorFetch;globalThis.window=priorWindow;
 }finally{dom.restore();}
});

test('R5: every body passes the same owner admission guard in the ordinary and the token-only pending branches',async()=>{
 const doc=r=>({ok:true,project:'book',root:'main.tex',current_revision:'owner:'+r,source_revision:'source:'+r,presentation_revision:'presentation:one',sections:[{id:'s',blocks:[]}],source_observation:{schema_version:'laplace.manuscript-source-observation/1',revision:'source:'+r,source_revision:'root',file_revisions:{'main.tex':r}}});
 const variants={'foreign-project':raw=>{raw.project='other';},'missing-current-revision':raw=>{delete raw.current_revision;},'wrong-observation-schema':raw=>{raw.source_observation.schema_version='wrong';},valid:()=>{}};
 for(const [kind,mutate] of Object.entries(variants))for(const tokenOnly of [false,true]){
  const raw=doc('B');mutate(raw);let current=doc('A'),heads=0,dirty=tokenOnly;const applied=[];
  const walk={ready:()=>true,documentVersion:()=>manuscriptDocumentVersion(current),sourceObservation:()=>current,editState:()=>({dirty}),refresh:async options=>{applied.push(options.document.project);current=options.document;return true;}};
  const c=createManuscriptRefresh({project:'book',getWalk:()=>walk,visible:()=>true,observe:async()=>++heads===1?{...doc('B'),summary_revision:'sha256:'+'b'.repeat(64)}:{project:'book',unchanged:true,summary_revision:'sha256:'+'b'.repeat(64),document_status:'READY',as_of:'now'},read:async()=>raw,status(){}});
  const first=await c.check();dirty=false;const recovered=tokenOnly?await c.settled():first;
  if(kind==='valid'){assert.equal(recovered.refreshed,true,kind+' '+tokenOnly);assert.deepEqual(applied,['book']);assert.equal(c.pending,false);assert.equal(current.current_revision,'owner:B');}
  else{assert.equal(recovered.checked,false,kind+' '+tokenOnly);assert.match(recovered.error,/incompatible source observation coordinates/);assert.deepEqual(applied,[],'an inadmissible body is never applied');assert.equal(c.pending,true,'the pending target survives the refusal');assert.equal(current.current_revision,'owner:A');}
  c.destroy();
 }
});


// ACTUAL-C8-EXCERPT-MARKUP / ACTUAL-C7-REFRESH-ERROR-COPY (root actual feedback, grouped with repair1 2026-10-14)
test('a shortened thread excerpt is a plain preview, never Markdown cut mid-construct; the whole reply keeps its formatted rendering',()=>{
 const dom=installDOM();try{
  const rendered=[];const current={project:'p',onApplication(){},guard:fn=>fn(),onOpenArtifact(){},status(){},authorMessage(){},actions(){},failures(){},remoteHistory(){},renderFinalMessage:(body,text)=>{rendered.push(text);body.textContent='<rendered>'+text;},
   message:WorkspaceSession.prototype.message,find:()=>({remove(){},append(){}}),onReadTurn:null,parentContinuationValue:null};
  current.facets=WorkspaceSession.prototype.facets;current.proposal=WorkspaceSession.prototype.proposal;current.appendTurn=WorkspaceSession.prototype.appendTurn;
  const thread=new Node('div');current.find=selector=>selector==='[data-thread]'?thread:{remove(){}};
  current.appendTurn({id:'t1',text:'Request',reply:{display_text:'A list:\n- one\n- `two',display_text_truncated:true,display_text_chars:4000,status:'completed'},result_links:[]},false);
  const excerpt=thread.children.at(-1);assert.ok(excerpt.className.includes('is-excerpt'));assert.equal(rendered.length,0,'the excerpt is not rendered as Markdown');
  assert.ok(excerpt.textContent.includes('- `two'),'the partial text is shown as plain text');assert.ok(!excerpt.all().some(n=>n.tag==='a'),'no link is parsed out of a partial preview');assert.ok(excerpt.textContent.includes('Reply shortened'));
  current.appendTurn({id:'t2',text:'Request',reply:{display_text:'Whole **reply**',status:'completed'},result_links:[]},false);
  assert.deepEqual(rendered,['Whole **reply**'],'a complete reply keeps the formatted rendering');
 }finally{dom.restore();}
});
test('a failed manuscript refresh says what stands in the reader\'s words and keeps the exact owner detail for inspection',async()=>{
 const current={project:'book',current_revision:'owner:one',sections:[],source_observation:{schema_version:'laplace.manuscript-source-observation/1',revision:'source:one',source_revision:'root',file_revisions:{}}};
 const walk={ready:()=>true,documentVersion:()=>manuscriptDocumentVersion(current),sourceObservation:()=>current,editState:()=>({}),refresh:async()=>{}};
 const notices=[];
 const control=createManuscriptRefresh({project:'book',observe:async()=>({project:'other',unchanged:true,summary_revision:'sha256:'+'b'.repeat(64)}),read:async()=>{throw Error('no');},getWalk:()=>walk,visible:()=>true,status:(text,error,owner)=>notices.push({text,error,owner})});
 try{const result=await control.check();assert.equal(result.checked,false);assert.match(result.error,/incompatible/);
  const last=notices.at(-1);assert.ok(last.error);assert.ok(!/incompatible|coordinates|owner/.test(last.text),'no protocol terms in the banner: '+last.text);
  assert.match(last.text,/could not be refreshed/);assert.match(last.text,/tries again on its own/);assert.ok(!/reload/i.test(last.text),'no reload advice');
  assert.equal(last.owner.kind,'manuscript-refresh-failure');assert.match(last.owner.detail,/incompatible source observation coordinates/,'the exact owner message is on the failure owner for inspection');
  assert.equal(typeof last.owner.retry,'function','the failure offers Try again now');
 }finally{control.destroy();}
});
// repair2 R5: the words follow the draft state and never advise a reload while text is unsaved
test('the refresh failure copy is draft-safe: clean, dirty and failed-save states each say what stands without reload advice',async()=>{
 for(const [state,expect] of [[{},/last version read/],[{dirty:true},/unsaved edits are kept in the editor; keep this page open/],[{dirty:true,persistence:{status:'failed'}},/not saved yet; keep this page open and save them before leaving/]]){
  const current={project:'book',current_revision:'owner:one',sections:[],source_observation:{schema_version:'laplace.manuscript-source-observation/1',revision:'source:one',source_revision:'root',file_revisions:{}}};
  const walk={ready:()=>true,documentVersion:()=>manuscriptDocumentVersion(current),sourceObservation:()=>current,editState:()=>state,refresh:async()=>{}};const notices=[];
  const control=createManuscriptRefresh({project:'book',observe:async()=>{throw Error('synthetic owner refusal');},read:async()=>{throw Error('no');},getWalk:()=>walk,visible:()=>true,status:(text,error,owner)=>notices.push({text,error,owner})});
  try{await control.check();const n=notices.at(-1);assert.match(n.text,expect,JSON.stringify(state));assert.ok(!/reload/i.test(n.text));assert.equal(n.owner.detail,'synthetic owner refusal');
   // Try again now runs the same guarded check (still refused here, pending kept)
   const again=await n.owner.retry();assert.equal(again.checked,false);assert.equal(control.pending,true);
  }finally{control.destroy();}
 }
});
test('the shell status line offers Try again now and a keyboard-reachable Details control with the exact owner message',async()=>{
 const shell=src('static_shared/workspace-notices.mjs');   // the status line owner (M5 S2 F1)
 const start=shell.indexOf('  const noticeRecovery=');const end=shell.indexOf('host.append(\' \',toggle,\' \',detail);}};',start);
 assert.ok(start>0&&end>start);const code=shell.slice(start,end)+"host.append(' ',toggle,' ',detail);}};";
 const dom=installDOM();try{
  const E=(tag,text='',cls='')=>{const n=new Node(tag);n.textContent=text;n.className=cls;return n;};globalThis.__E=E;
  const mod=await import('data:text/javascript;base64,'+Buffer.from('const E=globalThis.__E;'+code.replace('  const noticeRecovery=','const noticeRecovery=')+'\nexport {noticeRecovery};').toString('base64'));
  const host=new Node('p');let retried=0;mod.noticeRecovery(host,{kind:'manuscript-refresh-failure',detail:'The document owner returned incompatible source observation coordinates.',at:1,retry:async()=>{retried++;}});
  const buttons=host.all().filter(n=>n.tag==='button');assert.deepEqual(buttons.map(b=>b.textContent),['Try again now','Details']);
  const detail=host.all().find(n=>n.className==='notice-detail');assert.equal(detail.hidden,true);assert.equal(buttons[1].attrs['aria-controls'],detail.id);
  buttons[1].onclick();assert.equal(detail.hidden,false);assert.equal(buttons[1].attrs['aria-expanded'],'true');assert.match(detail.textContent,/incompatible source observation coordinates/);
  await buttons[0].onclick();assert.equal(retried,1);
  const plain=new Node('p');mod.noticeRecovery(plain,null);assert.equal(plain.children.length,0,'an ordinary notice has no controls');
  assert.ok(!/data-notice\]'\)\.title=owner/.test(shell),'the owner detail is not a tooltip');
 }finally{delete globalThis.__E;dom.restore();}
});
