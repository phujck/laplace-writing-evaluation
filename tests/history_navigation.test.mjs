import {test} from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
import {register} from 'node:module';register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
// the history helpers are the real facade exports (workspace-activity, -research, -manuscript; M5 S2 F1)
const source=(await import('./helpers/workspace_source.mjs')).workspaceSource();
const {focusHistoryResearchTarget,manuscriptPassageTarget,historyScopeForView,historyTargetUnavailable,historyManuscriptRoute}=await import('../src/laplace/web/static_shared/workspace.mjs');
const blocks=[{id:'first',file:'chapters/one.tex',line_start:8,line_end:10,text:'First chapter.'},{id:'second',file:'chapters/two.tex',line_start:15,line_end:18,text:'Second chapter.'},{id:'following',file:'chapters/two.tex',line_start:20,line_end:22,text:'Following paragraph.'}];
test('History file-only links open the first rendered block in the exact selected file',()=>{assert.equal(manuscriptPassageTarget(blocks,{file:'chapters/two.tex'}).id,'second');assert.equal(manuscriptPassageTarget(blocks,{file:'project/manuscript/chapters/two.tex'}).id,'second');assert.equal(manuscriptPassageTarget(blocks,{file:'unselected.tex'}),null);assert.equal(manuscriptPassageTarget(blocks,{}),null);});
test('recorded line spans are never silently changed into file-start navigation',()=>{assert.equal(manuscriptPassageTarget(blocks,{file:'chapters/two.tex',line_start:21}).id,'following');assert.equal(manuscriptPassageTarget(blocks,{file:'chapters/two.tex',line_start:300}),null);assert.equal(manuscriptPassageTarget(blocks,{file:'chapters/two.tex',line_start:300,quote:'Following paragraph.'}).id,'following');});
test('History scope follows the actual selected view and does not reuse stale logical attention',()=>{assert.deepEqual(historyScopeForView('manuscript',{block:blocks[1],attention:{label:'Second chapter'},logical:{id:'old'}}),{file:'chapters/two.tex',label:'Second chapter'});assert.deepEqual(historyScopeForView('research',{attention:{result_id:'result:one',label:'One result'},logical:{id:'old'}}),{result_id:'result:one',label:'One result'});assert.deepEqual(historyScopeForView('research',{attention:null,logical:{id:'old'}}),{});assert.deepEqual(historyScopeForView('overview',{logical:{id:'old'}}),{});});
test('formal History links require their canonical target instead of guessing from a receipt ID',()=>{assert.ok(historyTargetUnavailable({kind:'formal',id:'PROOF-one'}));assert.equal(historyTargetUnavailable({kind:'formal',id:'PROOF-one',concept_id:'claim:one'}),null);assert.ok(historyTargetUnavailable({kind:'manuscript'}));});

test('explicit History result navigation waits for rendering before resetting its reader and keeps History return state',async()=>{
 const history={scrollTop:870,expanded:'activity:research:one'},main={scrollTop:870,querySelectorAll:()=>[card]},focused=[],selected=[],rendered=[];
 const card={dataset:{researchId:'result:one'},focus:options=>focused.push(options)};let finish;
 const show=()=>new Promise(resolve=>{finish=()=>{main.scrollTop=410;rendered.push(true);resolve();};});
 const body=source.slice(source.indexOf('  async function openEvidence('),source.indexOf('\n  return {',source.indexOf('  async function openEvidence(')));
 const open=new Function('focusResearchResult','saveResearchNavigation','views','ui','focusHistoryResearchTarget',`const project='fixture',literatureTarget=null,literatureReader=null;let researchTab;${body};return openEvidence;`)((...args)=>selected.push(args),()=>{},{show},{main:()=>main,notice:()=>{}},focusHistoryResearchTarget);
 const pending=open('result:one',{fromHistory:true});assert.equal(main.scrollTop,870);assert.equal(focused.length,0);finish();await pending;
 assert.equal(rendered.length,1);assert.equal(main.scrollTop,0);assert.deepEqual(focused,[{preventScroll:true}]);assert.deepEqual(selected,[['fixture','result:one','numerics']]);assert.deepEqual(history,{scrollTop:870,expanded:'activity:research:one'});
});

test('one source identity: repo_file matches exactly, an UNPROVED basename never places a block',()=>{
 const rows=[{id:'a',file:'chapters/one.tex',repo_file:'papers/alpha/chapters/one.tex',line_start:1,line_end:4,text:'Alpha one.'},{id:'b',file:'chapters/one.tex',repo_file:'papers/beta/chapters/one.tex',line_start:1,line_end:4,text:'Beta one.'}];
 assert.equal(manuscriptPassageTarget(rows,{file:'papers/beta/chapters/one.tex',repo_file:'papers/beta/chapters/one.tex',binding:'BOUND'}).id,'b');
 assert.equal(manuscriptPassageTarget(rows,{file:'papers/alpha/chapters/one.tex',repo_file:'papers/alpha/chapters/one.tex',binding:'BOUND',line_start:2}).id,'a');
 assert.equal(manuscriptPassageTarget(rows,{file:'one.tex',binding:'UNPROVED'}),null,'a historical basename is never guessed into a same-named file');
 assert.equal(manuscriptPassageTarget(rows,{file:'chapters/one.tex'}).id,'a','a manuscript-relative file without a repo path keeps the exact-file match');
 assert.equal(manuscriptPassageTarget(rows,{repo_file:'papers/gamma/chapters/one.tex',file:'papers/gamma/chapters/one.tex',binding:'BOUND'}),null,'a bound path outside the selected manuscript matches nothing');
});

// Root B1 (UNPROVED): the route of a History manuscript target is decided before any view
// transition, so the record inspector opens over History and closing it leaves History.
test('History manuscript routes are decided from the owner binding and loaded blocks, never by loading first',async()=>{
 const rows=[{id:'a',file:'chapters/chapter-01.tex',repo_file:'papers/alpha/chapters/chapter-01.tex',line_start:1,line_end:4,text:'Alpha.'}];
 const unproved=historyManuscriptRoute({kind:'manuscript',file:'chapters/chapter-01.tex',binding:'UNPROVED'},null);
 assert.equal(unproved.route,'record');assert.equal(unproved.state,'UNPROVED');
 assert.match(unproved.notice,/records chapters\/chapter-01\.tex without a proven checkout binding/,'the copy states the recorded path, not "a file name"');
 assert.doesNotMatch(unproved.notice,/names only a file name/);
 assert.equal(historyManuscriptRoute({kind:'manuscript',file:'chapters/chapter-01.tex',repo_file:'papers/alpha/chapters/chapter-01.tex',binding:'BOUND'},rows).route,'passage');
 const absent=historyManuscriptRoute({kind:'manuscript',file:'chapters/chapter-02.tex',repo_file:'papers/alpha/chapters/chapter-02.tex',binding:'BOUND'},rows);
 assert.equal(absent.route,'record');assert.equal(absent.state,'ABSENT');assert.match(absent.notice,/not in the currently selected manuscript/);
 assert.equal(historyManuscriptRoute({kind:'manuscript',file:'chapters/chapter-02.tex',repo_file:'papers/alpha/chapters/chapter-02.tex',binding:'BOUND'},null).route,'load','only an unloaded manuscript needs loading to prove a bound placement');
 assert.equal(historyManuscriptRoute({kind:'manuscript',file:'figures/plot.pdf',binding:'BOUND'},null).route,'artifact');
});

test('the actual History open handler never loads the manuscript for an UNPROVED or absent target and keeps History',async()=>{
 const start=source.indexOf('      onOpenTarget:async(target,intent)=>{'),end=source.indexOf('      onOpenConversation:async target=>{',start);
 const handler=source.slice(start,end).replace("await import('/shared/workspace-analytics.mjs')",'analyticsModule').replace(/^\s*onOpenTarget:/,'').replace(/,\s*$/,'');
 const build=(blocks)=>{const calls={ready:0,remembered:0,passages:[],records:[],notices:[],artifacts:[]};
  const fn=new Function('analyticsModule','manuscriptPassageTarget','historyManuscriptRoute','calls','blocks',`
   // the services mountActivity receives from the shell (M5 S2 F1), as plain recording stubs
   const project='P',api=async()=>({}),forms={leave:()=>true},ui={root:{isConnected:true},notice:(text,error)=>calls.notices.push([text,!!error]),$:()=>({querySelector:()=>null})};
   const place={remember:()=>{calls.remembered++;}},views={show:async()=>{},current:()=>'history'};
   const manuscript={sourceWindow:()=>blocks?{walk:{blocks:()=>blocks}}:undefined,
     ready:async()=>{calls.ready++;return {blocks:()=>[{id:'a',file:'chapters/chapter-01.tex',repo_file:'papers/alpha/chapters/chapter-01.tex',line_start:1,line_end:4,text:'Alpha.'}]};},
     inspectPassage:async anchor=>{calls.passages.push(anchor);}};
   const inspect={projectArtifact:async(file,label)=>{calls.artifacts.push([file,label]);},ownerRead:async()=>{}};
   const research={openEvidence:async()=>{},openFormal:async()=>{},openSource:async()=>{}},argument={openConcept:async()=>{}},discussion={open:()=>{},session:()=>({})};
   let reviewCorrection;
   return ${handler};`);
  const analyticsModule={readAnalyticsRecord:async(handle,options)=>{calls.records.push({handle,options});}};
  return {calls,open:fn(analyticsModule,manuscriptPassageTarget,historyManuscriptRouteOf(),calls,blocks)};};
 const historyManuscriptRouteOf=()=>historyManuscriptRoute;
 // UNPROVED editor-save record, manuscript not loaded (the rehearsal History pane).
 let {calls,open}=build(null);
 await open({kind:'manuscript',file:'chapters/chapter-01.tex',binding:'UNPROVED',history_id:'activity:authoring:FB-20261012-082824-chapters/chapter-01.tex'});
 assert.equal(calls.ready,0,'no manuscript load');assert.equal(calls.remembered,0,'no view left, so no return remembered');assert.equal(calls.passages.length,0);
 assert.equal(calls.records.length,1);assert.equal(calls.records[0].handle.payload.id,'activity:authoring:FB-20261012-082824-chapters/chapter-01.tex');
 assert.equal(new URL(calls.records[0].handle.http.url,'http://x').searchParams.get('id'),'activity:authoring:FB-20261012-082824-chapters/chapter-01.tex');
 assert.deepEqual(calls.notices,[['This saved version records chapters/chapter-01.tex without a proven checkout binding. Its saved text is shown from the record; no current file is guessed.',false]]);
 // Bound path absent from the selected document while the manuscript is already loaded: no transition either.
 ({calls,open}=build([{id:'a',file:'chapters/chapter-01.tex',repo_file:'papers/alpha/chapters/chapter-01.tex',line_start:1,line_end:4,text:'Alpha.'}]));
 await open({kind:'manuscript',file:'chapters/chapter-02.tex',repo_file:'papers/alpha/chapters/chapter-02.tex',binding:'BOUND',history_id:'activity:authoring:two'});
 assert.equal(calls.ready,0);assert.equal(calls.remembered,0);assert.equal(calls.records.length,1);assert.match(calls.notices[0][0],/not in the currently selected manuscript/);
 // Bound path placed in the loaded manuscript: the passage opens (inspectPassage remembers the return itself).
 ({calls,open}=build([{id:'a',file:'chapters/chapter-01.tex',repo_file:'papers/alpha/chapters/chapter-01.tex',line_start:1,line_end:4,text:'Alpha.'}]));
 await open({kind:'manuscript',file:'chapters/chapter-01.tex',repo_file:'papers/alpha/chapters/chapter-01.tex',binding:'BOUND',history_id:'activity:authoring:one'});
 assert.equal(calls.ready,0);assert.equal(calls.passages.length,1);assert.equal(calls.records.length,0);
 // Bound path with no loaded manuscript: loading is the only way to prove placement, and the return is remembered first.
 ({calls,open}=build(null));
 await open({kind:'manuscript',file:'chapters/chapter-01.tex',repo_file:'papers/alpha/chapters/chapter-01.tex',binding:'BOUND',history_id:'activity:authoring:one'});
 assert.equal(calls.ready,1);assert.equal(calls.remembered,1);assert.equal(calls.passages.length,1);
 // UNPROVED without a record id: an error notice, still no transition.
 ({calls,open}=build(null));
 await open({kind:'manuscript',file:'chapter-01.tex',binding:'UNPROVED'});
 assert.equal(calls.ready,0);assert.equal(calls.records.length,0);assert.equal(calls.notices[0][1],true);
});
