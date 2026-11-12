import {requireSourceCompletion,sourceEffectFromError} from '../src/laplace/web/static_shared/source-effect.mjs';
import {readManuscriptSource,saveManuscriptSource,advanceSourceObservation,readHistoricalSource} from '../src/laplace/web/static_shared/manuscript-source-client.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {execFileSync} from 'node:child_process';

// Execute the actual adapter functions with the existing owner gateway stubbed.
// No copied save algorithm and no browser/server or source fixture mutation.
const source = fs.readFileSync(new URL('../src/laplace/web/static_shared/artefact-panes.mjs', import.meta.url), 'utf8');
const between = (a, b) => source.slice(source.indexOf(a), source.indexOf(b, source.indexOf(a)));
function deferred() { let resolve, reject; const promise = new Promise((a,b)=>{resolve=a;reject=b;}); return {promise,resolve,reject}; }
function harness(fetchJSON, overrides={}) {
  const state = {text:'old',messages:[],compiles:0};
  const ctx = vm.createContext({requireSourceCompletion,sourceEffectFromError,EDIT_EFFECT_HOLD:null,readManuscriptSource,saveManuscriptSource,advanceSourceObservation,store:{fetchJSON},CTX:{tex_endpoint:'/projection/tex',current_artefact:{tex:'main.tex'}},
    _corpus:()=> 'book',
    $:()=>({innerHTML:'',textContent:''}), $$:()=>[], esc:String,
    CM_VIEW:{state:{doc:{length:3}},dispatch:change=>{state.text=change.changes.insert;}},
    CM_MOD:null, ensureFollow(){}, async ensureHisHand(){}, async refreshVersions(){},
    editorText:()=>state.text, setEditMsg:(s)=>state.messages.push(s),
    sessionActor:()=> 'eigen:codex-ui-verification',
    startRecompile:async()=>{state.compiles++;}, currentRevision:()=>({tex:'main.tex'}),...overrides});
  vm.runInContext(`let EDIT_FILE=null,EDIT_SOURCE_DIGEST=null,EDIT_SOURCE_OBSERVATION=null,EDIT_LOAD_GENERATION=0;\n`+
    between('function compileParams(', 'async function ensureAssets()')+
    between('async function loadEditFile(file)', 'function editorText()')+
    between('async function saveTex()', 'async function startRecompile()')+
    between('let RESTORE_ARMED = null;', 'function infoTag(')+
    `\nglobalThis.adapter={loadEditFile,saveTex,saveAndRecompile,armRestore,scope:()=>({file:EDIT_FILE,digest:EDIT_SOURCE_DIGEST})};`,ctx);
  return {state,api:ctx.adapter};
}
const observed = (file,digest,content='loaded') => ({schema_version:'laplace.projection-source/1',file,content,expected_source_digest:'sha256:'+digest.repeat(64)});

test('file switch ignores an old read and save keeps the same physical owner basis',async()=>{
  const a=deferred(),b=deferred(),posts=[];
  const h=harness((path,opts)=>opts.method==='POST'?(posts.push(opts),Promise.resolve({ok:true,source_committed:true,file:opts.params.file,consumed_source_digest:opts.params.expected_source_digest,expected_source_digest:'sha256:'+'c'.repeat(64)})):opts.params.file==='a.tex'?a.promise:b.promise);
  const first=h.api.loadEditFile('a.tex'),second=h.api.loadEditFile('b.tex');
  b.resolve(observed('b.tex','b'));await second;a.resolve(observed('a.tex','a'));await first;
  assert.equal(h.api.scope().file,'b.tex');assert.equal(h.state.text,'loaded');
  h.state.text='draft';await h.api.saveTex();
  assert.equal(posts[0].params.file,'b.tex');assert.equal(posts[0].params.expected_source_digest,'sha256:'+'b'.repeat(64));
  assert.equal(posts[0].params.author,'eigen:codex-ui-verification');
  assert.equal(posts[0].body,'draft');assert.equal(h.api.scope().digest,'sha256:'+'c'.repeat(64));
});

test('refusal preserves draft and never starts dependent compile or refreshes guard',async()=>{
  let reads=0;
  const h=harness((path,opts)=>opts.method==='POST'?Promise.reject(Error('409 stale source')):(reads++,Promise.resolve(observed('main.tex','a'))));
  await h.api.loadEditFile('main.tex');h.state.text='unsaved draft';await h.api.saveAndRecompile();
  assert.equal(h.state.text,'unsaved draft');assert.equal(reads,1);assert.equal(h.state.compiles,0);
  assert.equal(h.api.scope().digest,'sha256:'+'a'.repeat(64));assert.match(h.state.messages.at(-1),/draft retained/);
});

test('late save acknowledgement retains new typing and cannot move a switched file basis',async()=>{
  const pending=deferred();const h=harness((path,opts)=>opts.method==='POST'?pending.promise:Promise.resolve(observed(opts.params.file,opts.params.file==='a.tex'?'a':'b')));
  await h.api.loadEditFile('a.tex');h.state.text='submitted';const saving=h.api.saveTex();h.state.text='new typing';
  pending.resolve({ok:true,source_committed:true,file:'a.tex',consumed_source_digest:'sha256:'+'a'.repeat(64),expected_source_digest:'sha256:'+'c'.repeat(64)});await saving;assert.equal(h.state.text,'new typing');
  const delayed=deferred();const j=harness((path,opts)=>opts.method==='POST'?delayed.promise:Promise.resolve(observed(opts.params.file,opts.params.file==='a.tex'?'a':'b')));
  await j.api.loadEditFile('a.tex');const old=j.api.saveAndRecompile();await j.api.loadEditFile('b.tex');delayed.resolve({ok:true,source_committed:true,file:'a.tex',consumed_source_digest:'sha256:'+'a'.repeat(64),expected_source_digest:'sha256:'+'c'.repeat(64)});await old;
  assert.equal(j.api.scope().digest,'sha256:'+'b'.repeat(64));assert.equal(j.state.compiles,0);
});

test('restore inspects the live target when armed and does not refresh at confirmation',async()=>{
  const requests=[];const h=harness((path,opts)=>{requests.push({path,opts});return Promise.resolve(opts.method==='POST'?{version_id:'new'}:observed('main.tex','a'));});
  const btn={dataset:{restore:'historical-v1',sourceFile:'main.tex'},textContent:''};await h.api.armRestore(btn);assert.equal(requests.length,1);await h.api.armRestore(btn);
  assert.equal(requests.length,2);assert.equal(requests[1].opts.params.version_id,'historical-v1');
  assert.equal(requests[1].opts.params.expected_source_digest,'sha256:'+'a'.repeat(64));
});


test('exact source acknowledgement survives post-effect attribution refresh failure',async()=>{
  const h=harness((path,opts)=>Promise.resolve(opts.method==='POST'
    ? {ok:true,source_committed:true,file:opts.params.file,consumed_source_digest:opts.params.expected_source_digest,expected_source_digest:'sha256:'+'b'.repeat(64)}
    : observed('main.tex','a')), {ensureHisHand:(()=>{let calls=0;return async()=>{if(++calls>1)throw Error('controlled maintenance failure');};})()});
  await h.api.loadEditFile('main.tex');h.state.text='authored';const saved=await h.api.saveTex();
  assert.equal(saved.expected_source_digest,'sha256:'+'b'.repeat(64));assert.equal(h.state.text,'authored');
  assert.equal(h.api.scope().digest,'sha256:'+'b'.repeat(64));assert.match(h.state.messages.at(-1),/source saved.*maintenance/);
  assert.ok(!h.state.messages.at(-1).includes('save failed'));
});

test('ordinary no-change acknowledgement says no duplicate history; structured conflict hides transport URL',async()=>{
 const h=harness((path,opts)=>Promise.resolve(opts.method==='POST'
  ?{ok:true,source_committed:true,changed:false,file:opts.params.file,consumed_source_digest:opts.params.expected_source_digest,expected_source_digest:opts.params.expected_source_digest}
  :observed('main.tex','a')));await h.api.loadEditFile('main.tex');await h.api.saveTex();assert.match(h.state.messages.at(-1),/No source changes.*no duplicate history/);
 const error=Object.assign(Error('fetchJSON POST /projection/tex?very-long-query →409'),{body:{reason:'source-revision-conflict'}});
 const refused=harness((path,opts)=>opts.method==='POST'?Promise.reject(error):Promise.resolve(observed('main.tex','a')));await refused.api.loadEditFile('main.tex');refused.state.text='Retain local draft';await refused.api.saveAndRecompile();assert.equal(refused.state.text,'Retain local draft');assert.equal(refused.state.compiles,0);assert.match(refused.state.messages.at(-1),/draft and original guard are retained/);assert.ok(!refused.state.messages.at(-1).includes('fetchJSON'));
});

test('actual follow observation is generation/file scoped; stale success/error cannot retire current note',async()=>{
 const first=deferred(),second=deferred(),paint=[];let calls=0;
 const ctx=vm.createContext({CTX:{current_artefact:{tex:'main.tex'}},_corpus:()=> 'book',currentRevision:()=>({tex:'main.tex'}),store:{fetchJSON:()=>++calls===1?first.promise:second.promise},renderFollow:()=>paint.push(ctx.read().follow)});
 vm.runInContext(`let EDIT_FILE='a.tex',EDIT_LOAD_GENERATION=1,FOLLOW={fresh:false};${between('function compileParams(', 'async function ensureAssets()')}${between('async function ensureFollow()', '// #3 — synctex at rest:')}globalThis.run=ensureFollow;globalThis.read=()=>({follow:FOLLOW});globalThis.switchFile=()=>{EDIT_FILE='b.tex';EDIT_LOAD_GENERATION++;};`,ctx);
 const a=ctx.run();ctx.switchFile();const b=ctx.run();second.resolve({fresh:true,file:'b.tex'});await b;first.reject(Error('late old failure'));await a;assert.equal(paint.length,1);assert.equal(ctx.read().follow.file,'b.tex');
});

test('both Follow directions carry declared root plus exact chapter and cannot paint a replaced root',async()=>{
 const calls=[],paint=[],goto=[],pending=deferred();let delayed=false;
 const ctx=vm.createContext({CTX:{current_artefact:{tex:'book/main.tex'}},_corpus:()=> 'book',currentRevision:()=>({tex:'book/main.tex'}),
  store:{fetchJSON:async(path,opts)=>{calls.push({path,...opts.params});if(delayed)return pending.promise;return path.endsWith('locate')?{page:1,x:2,y:3}:{file:'book/chapters/chapter.tex',line:6};}},
  scrollAndFlashPdf:(...args)=>paint.push(args),gotoSourceLine:(...args)=>goto.push(args),setFollowNote:()=>{},followFailure:()=>{}});
 vm.runInContext(`let EDIT_FILE='book/chapters/chapter.tex',EDIT_LOAD_GENERATION=1;${between('function compileParams(', 'async function ensureAssets()')}${between('async function locateFromSource(', 'async function gotoSourceLine(')}globalThis.fwd=locateFromSource;globalThis.rev=syncClickToSource;`,ctx);
 await ctx.fwd(6);await ctx.rev({page:1,px:2,py:3});assert.ok(calls.every(row=>row.file==='book/chapters/chapter.tex'&&row.compile_root==='book/main.tex'&&row.corpus==='book'));assert.equal(paint.length,1);assert.deepEqual(goto[0],['book/chapters/chapter.tex',6]);
 delayed=true;const old=ctx.fwd(6);ctx.CTX.current_artefact.tex='book/alternate.tex';pending.resolve({page:4,x:5,y:6});await old;assert.equal(paint.length,1);
});

for(const paused of ['log','reload','versions'])test('compile maintenance cannot paint a replaced root after '+paused,async()=>{
 const gate=deferred(),paint=[],reads=[],follow=[];let tick;
 const ctx=vm.createContext({CTX:{current_artefact:{tex:'A.tex'}},_corpus:()=> 'book',currentRevision:()=>({tex:ctx.CTX.current_artefact.tex,pdf:'B.pdf'}),
  setInterval:fn=>{tick=fn;return 1;},clearInterval:()=>{},store:{fetchJSON:async()=>({ok:true,state:'done',pdf:'A.pdf'})},
  fetchCompileLog:async()=>paused==='log'?gate.promise:{counts:{}},setEditMsg:text=>paint.push(text),renderCompileLog:()=>{},
  hotReloadEditPdf:async()=>{reads.push('reload');if(paused==='reload')await gate.promise;},
  refreshVersions:async()=>{reads.push('versions');if(paused==='versions')await gate.promise;},markReaderStale:value=>paint.push(value),ensureFollow:async()=>follow.push(true)});
 vm.runInContext(`let EDIT_FILE='chapter.tex',EDIT_LOAD_GENERATION=1,EDIT_PDF_REL=null,EDIT_PDF_TARGET=null,RECOMPILE_TIMER=null,MODE='edit';${between('function compileParams(', 'async function ensureAssets()')}${between('function activePdfRel()', 'async function loadReader(')}${between('function pollRecompile(', '// #6 — lead')}globalThis.begin=pollRecompile;globalThis.currentPdf=activePdfRel;globalThis.pdf=()=>EDIT_PDF_REL;`,ctx);
 ctx.begin();const pending=tick();await new Promise(resolve=>setImmediate(resolve));ctx.CTX.current_artefact.tex='B.tex';paint.length=0;reads.length=0;gate.resolve({counts:{}});await pending;
 assert.deepEqual(paint,[]);assert.deepEqual(reads,[]);assert.deepEqual(follow,[]);assert.equal(ctx.currentPdf(),'B.pdf');if(paused==='log')assert.equal(ctx.pdf(),null);
});

test('late reverse failure and compile-admission failure cannot paint the next selection',async()=>{
 const errors=[],first=deferred(),second=deferred();let calls=0;
 const ctx=vm.createContext({CTX:{current_artefact:{tex:'A.tex'}},_corpus:()=> 'book',currentRevision:()=>({tex:'A.tex'}),store:{fetchJSON:()=>++calls===1?first.promise:second.promise},
  followFailure:text=>errors.push(text),cleanErr:e=>e.message,setEditMsg:text=>errors.push(text),renderCompileLog:()=>{},pollRecompile:()=>{},gotoSourceLine:()=>{}});
 vm.runInContext(`let EDIT_FILE='chapter.tex',EDIT_LOAD_GENERATION=1;${between('function compileParams(', 'async function ensureAssets()')}${between('async function syncClickToSource(', 'async function gotoSourceLine(')}${between('async function startRecompile()', '// #5/#6 — read')}globalThis.reverse=syncClickToSource;globalThis.compile=startRecompile;`,ctx);
 const reverse=ctx.reverse({page:1,px:2,py:3}),compile=ctx.compile();errors.length=0;ctx.CTX.current_artefact.tex='B.tex';first.reject(Error('old reverse'));second.reject(Error('old compile'));await reverse;await compile;assert.deepEqual(errors,[]);
});

test('actual PDF renderer cannot publish a late document or error into a superseded target',async()=>{
 for(const failure of [false,true]){
  const pending=deferred(),into={innerHTML:'',dataset:{},classList:{toggle(){}}};let current=true;
  const ctx=vm.createContext({CTX:{pdf_endpoint:'/projection/pdf'},ensurePdfjs:async()=>({getDocument:()=>({promise:pending.promise})}),ec:encodeURIComponent,esc:String,ZOOM:1,window:{devicePixelRatio:1}});
  vm.runInContext(`let RENDER_SEQ=0,PDFDOC={name:'newer'};${between('async function renderPdf(', '// ACT 3: while MODE')}globalThis.render=renderPdf;globalThis.doc=()=>PDFDOC;`,ctx);
  const rendering=ctx.render('A.pdf',into,()=>current);await new Promise(resolve=>setImmediate(resolve));current=false;into.innerHTML='Current B';if(failure)pending.reject(Error('old render'));else pending.resolve({name:'old',numPages:0});await rendering;assert.equal(into.innerHTML,'Current B');assert.equal(ctx.doc().name,'newer');
 }
});

// Same version diff owner, with controlled exact read replies and a small focus DOM.
function diffHarness(fetchJSON, overrides = {}) {
 const classes=new Set(),root={classList:{contains:n=>classes.has(n),add:n=>classes.add(n),remove:n=>classes.delete(n)}};
 const state={project:'book',scrolls:[],focus:[],html:'',pair:['A','B']};let ctx;
 const opener={isConnected:true,focus(){state.focus.push('opener');ctx.document.activeElement=opener;}};
 const head={appendChild(){}};
 const pane={isConnected:true,classList:{add:n=>classes.add('pane:'+n),remove:n=>classes.delete('pane:'+n)},setAttribute(){},get innerHTML(){return state.html;},set innerHTML(v){state.html=v;},querySelector:()=>head,contains:n=>n===pane,focus(){state.focus.push('pane');ctx.document.activeElement=pane;}};
 const historicalTransport=async(path,options)=>{const content=await fetchJSON(path,options);if(typeof content!=='string')return content;const q=options.params;return {schema_version:'laplace.historical-source/1',project:q.project,file:q.file,content,content_revision:'sha256:'+'a'.repeat(64),archive_identity:{kind:q.kind,version_id:q.version_id,file:q.file,recorded_revision:null,verification:'OBSERVED_ONLY'},read_only:true,offset:0,total_characters:content.length,next_offset:null,next_read:null,complete:true};};
 ctx=vm.createContext({readHistoricalSource,store:{fetchJSON:historicalTransport},CTX:{corpus:'book',tex_endpoint:'/projection/tex',pdf_endpoint:'/projection/pdf'},VERS:{rows:['A','B','C'].map(id=>({_rid:id,paths:['versions/'+id+'.tex'],source_read:{method:'GET',route:'/authoring/history',query:{project:'book',view:'source',kind:'snapshot',version_id:id,file:'versions/'+id+'.tex'}}}))},RAILSEL:state.pair,DIFF_RESTORE_Y:0,DIFF_OPEN:null,DIFF_LAST:null,DIFF_GENERATION:0,DIFF_PROJECT:null,DIFF_OPENER:null,INSPECT_BUS:null,_soloFocus(){},_corpus:()=>state.project,$:id=>id==='#art'?root:id==='#art-diffpane'?pane:opener,document:{activeElement:opener},window:{scrollY:783,scrollTo:(x,y)=>state.scrolls.push([x,y])},esc:String,cut:(s,n)=>s.slice(0,n),returnDoor:()=>({}),ec:encodeURIComponent,...overrides});
 vm.runInContext(between('async function extractPdfText(', 'function lineDiff(')+between('function lineDiff(', '// ── The findings tray')+';globalThis.diffAPI={runDiff,closeDiff};',ctx);
 return {state,ctx,pane,root,opener,api:ctx.diffAPI};
}
test('version comparison reveals loading/current result and restores opener plus original scroll',async()=>{
 const requests=[],gate=deferred(),h=diffHarness((path,opts)=>{requests.push([path,opts]);return requests.length===1?gate.promise:Promise.resolve('after');});
 const pending=h.api.runDiff(h.opener);assert.match(h.state.html,/extracting text/);assert.match(h.state.html,/Close comparison/);assert.deepEqual(h.state.focus,['pane']);gate.resolve('before');await pending;
 assert.match(h.state.html,/2 changed line/);assert.match(h.state.html,/A ↔ B/);assert.equal(requests.length,2);assert.ok(requests.every(r=>r[0]==='/authoring/history'&&r[1].params.project==='book'));assert.deepEqual(requests.map(r=>r[1].params.file),['versions/A.tex','versions/B.tex']);
 h.api.closeDiff();assert.deepEqual(h.state.scrolls,[[0,783]]);assert.equal(h.state.focus.at(-1),'opener');assert.equal(h.root.classList.contains('is-diffing'),false);
});
test('closed diff ignores late success and does not start the second historical read',async()=>{
 const gate=deferred(),calls=[],h=diffHarness((...args)=>{calls.push(args);return gate.promise;});const pending=h.api.runDiff();h.api.closeDiff();const closed=h.state.html;gate.resolve('old');await pending;
 assert.equal(h.state.html,closed);assert.equal(calls.length,1);assert.equal(h.root.classList.contains('is-diffing'),false);assert.equal(h.state.focus.at(-1),'opener');
});
test('closed diff ignores late failure without stealing focus or repainting',async()=>{
 const gate=deferred(),h=diffHarness(()=>gate.promise);const pending=h.api.runDiff();h.api.closeDiff();const closed=h.state.html,focus=h.state.focus.length;gate.reject(Error('late error'));await pending;assert.equal(h.state.html,closed);assert.equal(h.state.focus.length,focus);
});
test('changed pair and project cannot redirect a pending second read or admit stale result',async()=>{
 for(const change of [h=>{h.ctx.RAILSEL=['A','C'];},h=>{h.state.project='other';}]){
  const gate=deferred(),calls=[],h=diffHarness((...args)=>{calls.push(args);return gate.promise;});const pending=h.api.runDiff();change(h);const prior=h.state.html;gate.resolve('old');await pending;assert.equal(calls.length,1);assert.equal(h.state.html,prior);
 }
});
test('a superseding same-pair comparison keeps its own result when the old reply arrives',async()=>{
 const gate=deferred();let calls=0;const h=diffHarness(()=>++calls===1?gate.promise:Promise.resolve(calls===2?'new before':'new after'));
 const old=h.api.runDiff();await h.api.runDiff();const current=h.state.html;assert.match(current,/new after/);gate.resolve('stale first');await old;assert.equal(h.state.html,current);assert.equal(calls,3);
});
test('current failures and unavailable versions retain a visible keyboard close route',async()=>{
 const failure=diffHarness(()=>Promise.reject(Error('exact read refused')));await failure.api.runDiff();assert.match(failure.state.html,/Comparison failed/);assert.match(failure.state.html,/exact read refused/);assert.match(failure.state.html,/Close comparison/);assert.equal(failure.state.focus.at(-1),'pane');
 const missing=diffHarness(()=>{throw Error('must not fetch');});missing.ctx.VERS.rows=[];await missing.api.runDiff();assert.match(missing.state.html,/Choose two available revisions/);assert.match(missing.state.html,/Close comparison/);
});

test('PDF-only history pair uses actual exact-file endpoint, not current-output qualification',async()=>{
 const owner=String.raw`import tempfile,json,sys
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from laplace.manuscript import projection_viewer as pv
with tempfile.TemporaryDirectory(prefix='laplace-pdf-owner-') as d:
 r=Path(d);md=r/'project/manuscript';md.mkdir(parents=True)
 (md/'main.tex').write_text('\\documentclass{article}\n\\begin{document}Current.\\end{document}')
 (r/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'book','project_dir':'project','tex_root':'project/manuscript','manifest':{'document':{'root':'project/manuscript/main.tex'}}}]}))
 for name in ('A','B'):
  (md/'archives').mkdir(exist_ok=True);(md/'archives'/f'{name}.pdf').write_bytes(f'Exact archived {name} bytes'.encode())
 pv._repo_root=lambda:r
 u=urlparse(sys.argv[1]);status,ctype,body=pv.handle(u.path,parse_qs(u.query),'GET',b'')
 print(json.dumps({'status':status,'ctype':ctype,'body':body.decode()}))`;
 const read=url=>JSON.parse(execFileSync('scripts/laplace-python',['-c',owner,url],{encoding:'utf8'}));const urls=[];
 const h=diffHarness(()=>{throw Error('must use PDF owner');},{ensurePdfjs:async()=>({getDocument:({url})=>({promise:Promise.resolve().then(()=>{urls.push(url);const response=read(url);assert.equal(response.status,200);assert.equal(response.ctype,'application/pdf');return {numPages:1,getPage:async()=>({getTextContent:async()=>({items:[{str:response.body,hasEOL:true}]})})};})})})});
 h.ctx.VERS.rows=[{_rid:'A',paths:['project/manuscript/archives/A.pdf']},{_rid:'B',paths:['project/manuscript/archives/B.pdf']}];await h.api.runDiff();
 assert.equal(urls.length,2,h.state.html);assert.ok(urls.every(url=>!new URL(url,'http://local').searchParams.has('corpus')));assert.match(h.state.html,/text-layer diff/);assert.match(h.state.html,/Exact archived A bytes/);assert.match(h.state.html,/Exact archived B bytes/);
 assert.equal(read(urls[0]+'&corpus=book').status,409); // Actual current-output guard stays intact.
});
