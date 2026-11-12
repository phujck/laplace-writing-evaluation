import {sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError} from '../src/laplace/web/static_shared/source-effect.mjs';
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {captureSourceChange,captureApplicationChange,historySpan} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {walkSource,walkDeclarations} from './helpers/walk_source.mjs';
// THE REQUEST, IN THE ONE SHAPE (WRITING-CONSOLIDATION-W1, the synthesis of storage-latency
// and editor-doors). Undo no longer builds its own body: it calls `sourceRequest` ->
// `retrySaveOnce`, the same producer and the same retry as the other three gestures, so the
// span and the bodies are in the GRAMMAR request (`target` = `<project>::<file>:<a>-<b>`,
// `payload.before_content`, `payload.after`) and not in three flat top-level keys. These
// tests read the span with walk.mjs's OWN `spanOf`, which is the only reader of either
// spelling, rather than with a second copy of the parsing here.
const addressed=(ctx,body)=>({...ctx.spanOf(body),
  before:(body.payload||body).before_content!==undefined?(body.payload||body).before_content:body.before,
  after:(body.payload||body).after!==undefined?(body.payload||body).after:body.after});
// The door's own splice, so a test proves the span the editor sends rebuilds the same
// file through the server's arithmetic (src/laplace/review_surface.py:2265) rather than
// through a whole-file replacement the editor happened to compute.
const doorSplice=(text,sent)=>{const lines=text.split('\n');return [...lines.slice(0,sent.line_start-1),...String(sent.after).split('\n'),...lines.slice(sent.line_end)].join('\n');};
const doorGuard=(text,sent)=>text.split('\n').slice(sent.line_start-1,sent.line_end).join('\n');
const source=walkSource();
// FOUR SLICES, because the undo's producers sit above it in the file and the point of this
// campaign is that the test drives the REAL ones: `sourceRequest`/`withNeeded`/`blockAtSpan`/
// `expectedOf`/`spanOf` (A), `retrySaveOnce` (B), the history and undo themselves (C), and
// `scopeFields`, which `sourceRequest` calls (D).
const sliceA=walkDeclarations('sourceRequest','spanOf','ownerView','withNeeded','setPayload','blockAtSpan','expectedOf','adoptBlockModel','captureBasis','assignBasis','basisOf',
 'verifyAwaiting','readdressDraft','awaitingUnread','REVIEW_WORDS');
const sliceB=walkDeclarations('sourceEffectRequest','retrySaveOnce');
const sliceD=source.slice(source.indexOf('function scopeFields('),source.indexOf('function containerToken('));
const body=sliceA+sliceB+walkDeclarations('rememberExternalTransaction','rememberExternalApplication','undoEditorChange')+sliceD;
const PRODUCERS=';this.spanOf=spanOf;this.sourceRequest=sourceRequest;';
function editor(kind){let persisted;const calls=[];const sandbox={S:{corpus:'book'},savedEditHistory:{undo:[],redo:[],external:new Set(),pending:[],busy:false},E:{dirty:false},P:new Map(),URLSearchParams,restoreEditHistory:()=>true,emit(){},persistEditHistory(){persisted={undo:[...sandbox.savedEditHistory.undo],redo:[...sandbox.savedEditHistory.redo],external:[...sandbox.savedEditHistory.external]};},window:{walk:{refresh:async()=>{}}},store:{fetchJSON:async(path,options)=>{calls.push({path,options});return options?{ok:true,undo:{operation:calls.filter(row=>row.options).length===1?'redo-operation':'undo-operation'}}:{undo:{operation:'undo-operation'}};}}};Object.assign(sandbox,{sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError});vm.createContext(sandbox);vm.runInContext(body+';this.register=rememberExternalTransaction;this.undo=undoEditorChange;',sandbox);return {sandbox,calls,persisted:()=>persisted,ref:{kind,id:'receipt-1',project:'book'}};}
for(const kind of ['block','section'])test(`recovered ${kind} change joins one Ctrl-Z history and lazily resolves its exact inverse`,async()=>{const {sandbox:e,calls,ref,persisted}=editor(kind);e.register({id:'action-1',undo_ref:ref});e.register({id:'action-1',undo_ref:ref});assert.equal(e.savedEditHistory.undo.length,1);assert.equal(calls.length,0);assert.equal(persisted().undo[0].undo,null);await e.undo(false);assert.equal(calls[0].path,'/authoring/structural-undo?project=book&kind='+kind+'&id=receipt-1');assert.equal(calls[1].path,'/authoring/'+kind+'-change');assert.equal(calls[1].options.body.operation,'undo-operation');await e.undo(true);assert.equal(calls.length,3);assert.equal(calls[2].options.body.operation,'redo-operation');await e.undo(false);e.savedEditHistory.redo=[];e.register({id:'action-1',undo_ref:ref});assert.equal(e.savedEditHistory.undo.length,0,'conversation reload cannot resurrect an already undone transaction after another edit');});
test('a receipt from another project is never admitted into the local history',()=>{const {sandbox:e,ref}=editor('block');e.register({id:'action-1',undo_ref:{...ref,project:'foreign'}});assert.equal(e.savedEditHistory.undo.length,0);});


test('conversation replay hydrates saved Redo before registering and later ready restores are idempotent',()=>{
 const setup=walkDeclarations('savedEditHistory','editHistoryLoadedFor','editorPersistence','storageFailure','storageRecovered','historyKey','persistEditHistory','restoreEditHistory');
 const registration=source.slice(source.indexOf('function rememberExternalTransaction('),source.indexOf('async function undoEditorChange('));
 const ref={kind:'block',id:'original',project:'book'},values=new Map([['laplace:editor-history:book',JSON.stringify({undo:[],redo:[{transaction:true,undo_ref:ref}],external:['block:original']})]]);
 const context={S:{corpus:'book'},authorChangeRecords:new Map(),emit(){},localStorage:{getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)}};
 Object.assign(context,{sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError});context.S ||= {corpus:"book"};vm.createContext(context);vm.runInContext(setup+registration+';this.restore=restoreEditHistory;this.register=rememberExternalTransaction;this.history=savedEditHistory;',context);
 context.register({id:'action',undo_ref:ref});assert.equal(context.history.redo.length,1);assert.equal(context.history.undo.length,0);
 context.history.redo.push({file:'another.tex'});context.restore();assert.equal(context.history.redo.length,2,'late ready callback cannot overwrite live history');assert.equal(JSON.parse(values.get('laplace:editor-history:book')).redo.length,1);
});

test('local history storage failures are reported without dropping the in-memory inverse',()=>{
 const setup=walkDeclarations('savedEditHistory','editHistoryLoadedFor','editorPersistence','storageFailure','storageRecovered','historyKey','persistEditHistory','restoreEditHistory');const events=[];
 const context={S:{corpus:'book'},authorChangeRecords:new Map(),emit:(kind,value)=>events.push({kind,value}),localStorage:{getItem:()=>null,setItem:()=>{throw Error('quota exceeded');}}};
 Object.assign(context,{sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError});context.S ||= {corpus:"book"};vm.createContext(context);vm.runInContext(setup+';this.restore=restoreEditHistory;this.persist=persistEditHistory;this.history=savedEditHistory;',context);context.restore();context.history.redo.push({file:'main.tex',before:'A',after:'B'});assert.equal(context.persist(),false);assert.equal(context.history.redo.length,1);assert.equal(events[0].kind,'persistence-status');assert.match(events[0].value.history,/quota exceeded/);
});

test('the writer inverse is persisted before asynchronous rendering completes',async()=>{
 const {sandbox:e,persisted,ref}=editor('block');e.register({id:'action',undo_ref:ref});let release;e.window.walk.refresh=()=>new Promise(resolve=>{release=resolve;});const pending=e.undo(false);while(!release)await Promise.resolve();assert.equal(persisted().redo.length,1);assert.equal(persisted().undo.length,0);release();await pending;
});

test('thin application handles fetch exact edits only on Undo and preserve source guards, order and Redo',async()=>{
 let text='Heading\nNew first.\nMiddle\nNew second.\nTail';const original=text,calls=[],events=[];
 const application={id:'WA-one',complete:true,receipts:[{record:{anchor:{file:'chapter.tex',lines:[1,5],after:original}}}],edits:[{file:'chapter.tex',line_start:2,before:'Old first.',after:'New first.'},{file:'chapter.tex',line_start:4,before:'Old second.',after:'New second.'}]};
 // `S.blocks` is EMPTY here on purpose: this fixture publishes no canvas, so `blockAtSpan`
 // finds nothing and `expected` is `[]` --- the declared path where the door's byte guard
 // decides. The token path is the test below it.
 const context={S:{corpus:'book',blocks:[]},C:{actor:'author'},srcOf:b=>({file:(b.src||{}).file||'',lineStart:Number((b.src||{}).line_start||0),lineEnd:Number((b.src||{}).line_end||0)}),E:{dirty:false},P:new Map(),savedEditHistory:{undo:[],redo:[],external:new Set(),pending:[],busy:false},URLSearchParams,restoreEditHistory:()=>true,persistEditHistory(){},emit:(kind,value)=>events.push({kind,value}),captureSourceChange,captureApplicationChange,historySpan,readEditorSource:async()=>text,ADJUDICATE:'/review/adjudicate',appliedOf:()=>true,window:{walk:{refresh:async()=>{}}},store:{fetchJSON:async(path,options)=>{calls.push({path,options});if(!options)return {project:'book',application};const sent=addressed(context,options.body);assert.equal(options.body.concept,'prose@paragraph','the undo posts the grammar request, like every other gesture');assert.equal(sent.before,doorGuard(text,sent),'the byte guard is the span the door will splice');assert.ok(sent.before.length<=text.length,'the row is never larger than the file');text=doorSplice(text,sent);return {ok:true};}}};Object.assign(context,{sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError});context.S ||= {corpus:"book"};vm.createContext(context);vm.runInContext(body+PRODUCERS+';this.register=rememberExternalApplication;this.undo=undoEditorChange;',context);
 const reference={id:'WA-one',project:'book',edit_count:2,detail:{turn_id:'turn-one',view:'application',item_id:'WA-one'}};context.register(reference);context.register(reference);assert.equal(context.savedEditHistory.undo.length,2);assert.equal(calls.length,0);await context.undo();assert.ok(text.includes('Old second.'));assert.ok(text.includes('New first.'));assert.match(calls[0].path,/view=application&item_id=WA-one/);await context.undo();assert.ok(text.includes('Old first.'));await context.undo(true);await context.undo(true);assert.equal(text,original);assert.equal(calls.filter(row=>!row.options).length,2,'one exact read per invoked edit, none during summary hydration');assert.equal(events.filter(row=>row.value.error).length,0);
 context.register({...reference,id:'WA-other',project:'foreign'});assert.equal(context.savedEditHistory.undo.length,2);
});
test('a lazy saved application cannot overwrite changed source or consume its Undo entry on failure',async()=>{
 const calls=[],events=[],ref={project:'book',turn_id:'turn',view:'application',item_id:'WA-one',index:0},change={application_id:'WA-one',edit_id:'0',application_ref:ref};const context={S:{corpus:'book'},C:{actor:'author'},E:{dirty:false},P:new Map(),savedEditHistory:{undo:[change],redo:[],external:new Set(),pending:[],busy:false},URLSearchParams,restoreEditHistory:()=>true,persistEditHistory(){},emit:(kind,value)=>events.push({kind,value}),captureSourceChange,captureApplicationChange,historySpan,readEditorSource:async()=>'The author has changed this passage.',store:{fetchJSON:async(path,options)=>{calls.push({path,options});return {project:'book',application:{id:'WA-one',complete:true,receipts:[{record:{anchor:{file:'chapter.tex',lines:[1,1],after:'Recorded applied text.'}}}],edits:[{file:'chapter.tex',line_start:1,before:'Old text.',after:'Recorded applied text.'}]}};}}};Object.assign(context,{sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError});context.S ||= {corpus:"book"};vm.createContext(context);vm.runInContext(body+';this.undo=undoEditorChange;',context);await context.undo();assert.equal(calls.length,1);assert.equal(calls[0].options,undefined);assert.equal(context.savedEditHistory.undo.length,1);assert.equal(context.savedEditHistory.redo.length,0);assert.ok(events.some(row=>row.value.error&&row.value.text.includes('could not safely locate')));assert.equal(change.require_context,true);
});

test('a saved paragraph with section context uses the guarded source inverse, not structural Undo',async()=>{
 let text='Unrelated new opening.\nHeading\nThe packaged editor saves this change.\nTail',calls=[];
 const change=captureSourceChange('Heading\nThe packaged editor saves this change.\nTail',{file:'chapter.tex',line_start:2,before:'Test whether a fresh unrelated project can be created and opened.',after:'The packaged editor saves this change.',section:'chapter-one'});
 assert.equal(change.section,'chapter-one');
 // THE CANVAS PUBLISHED A TOKEN FOR EXACTLY THAT SPAN, so the undo carries it: this is the
 // bridge between the two lanes (`blockAtSpan` -> `expectedOf`), and it only exists because
 // the span is the hunk. A request addressed at the whole file has a `prose` home nothing
 // published a token for, which is why the editor-doors lane could not gate this gesture and
 // left it as a residual for the storage lane's span.
 const blocks=[{src:{file:'chapter.tex',line_start:3,line_end:3},expected:['rev:prose:book::chapter.tex:3-3:abc']}];
 const context={S:{corpus:'book',blocks},C:{actor:'author'},srcOf:b=>({file:(b.src||{}).file||'',lineStart:Number((b.src||{}).line_start||0),lineEnd:Number((b.src||{}).line_end||0)}),E:{dirty:false},P:new Map(),savedEditHistory:{undo:[change],redo:[],external:new Set(),pending:[],busy:false},URLSearchParams,restoreEditHistory:()=>true,persistEditHistory(){},emit(){},readEditorSource:async()=>text,historySpan,ADJUDICATE:'/review/adjudicate',appliedOf:()=>true,window:{walk:{refresh:async()=>{}}},store:{fetchJSON:async(path,options)=>{calls.push({path,options});text=doorSplice(text,addressed(context,options.body));return {ok:true};}}};
 Object.assign(context,{sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError});context.S ||= {corpus:"book"};vm.createContext(context);vm.runInContext(body+PRODUCERS+';this.undo=undoEditorChange;',context);await context.undo();
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/review/adjudicate');
 const sent=calls[0].options.body,span=addressed(context,sent);
 // ONE REQUEST SHAPE: the gesture posts verb x concept with the span in its `target`, which
 // is what makes `expected` addressable at all.
 assert.equal(sent.verb,'change');assert.equal(sent.concept,'prose@paragraph');
 assert.equal(sent.target,'book::chapter.tex:3-3');
 assert.deepEqual(sent.expected,['rev:prose:book::chapter.tex:3-3:abc']);
 // THE HUNK SPAN, not the file: the row carries the one line the inverse touches, and
 // the passage he typed over beside it, so anchor.quote is the passage and not a third
 // copy of the chapter (src/laplace/review_surface.py:2134).
 assert.equal(span.before,'The packaged editor saves this change.');
 assert.equal(span.after,'Test whether a fresh unrelated project can be created and opened.');
 assert.equal(span.line_start,3);assert.equal(span.line_end,3);
 assert.equal(sent.payload.passage_before,'The packaged editor saves this change.');
 assert.equal(sent.payload.passage_after,'Test whether a fresh unrelated project can be created and opened.');
 assert.equal(text,'Unrelated new opening.\nHeading\nTest whether a fresh unrelated project can be created and opened.\nTail','the door\'s own splice of that span rebuilds the undone file');
 assert.equal(context.savedEditHistory.undo.length,0);assert.equal(context.savedEditHistory.redo.length,1);
});

test('an undo whose hunk is not one published block sends no token, and the byte guard decides',async()=>{
 // The declared normal path, asserted rather than described: `blockAtSpan` is EXACT match or
 // nothing, because a `prose` token is minted over the bytes of the span the request names
 // (review_surface._span_identities), so a token for a wider or narrower span is a home the
 // door does not address and sending it would be a refusal the retry cannot cure.
 let text='Unrelated new opening.\nHeading\nThe packaged editor saves this change.\nTail',calls=[];
 const change=captureSourceChange('Heading\nThe packaged editor saves this change.\nTail',{file:'chapter.tex',line_start:2,before:'Test whether a fresh unrelated project can be created and opened.',after:'The packaged editor saves this change.',section:'chapter-one'});
 const blocks=[{src:{file:'chapter.tex',line_start:1,line_end:4},expected:['rev:prose:book::chapter.tex:1-4:whole']}];
 const context={S:{corpus:'book',blocks},C:{actor:'author'},srcOf:b=>({file:(b.src||{}).file||'',lineStart:Number((b.src||{}).line_start||0),lineEnd:Number((b.src||{}).line_end||0)}),E:{dirty:false},P:new Map(),savedEditHistory:{undo:[change],redo:[],external:new Set(),pending:[],busy:false},URLSearchParams,restoreEditHistory:()=>true,persistEditHistory(){},emit(){},readEditorSource:async()=>text,historySpan,ADJUDICATE:'/review/adjudicate',appliedOf:()=>true,window:{walk:{refresh:async()=>{}}},store:{fetchJSON:async(path,options)=>{calls.push({path,options});text=doorSplice(text,addressed(context,options.body));return {ok:true};}}};
 Object.assign(context,{sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError});context.S ||= {corpus:"book"};vm.createContext(context);vm.runInContext(body+PRODUCERS+';this.undo=undoEditorChange;',context);await context.undo();
 assert.equal(calls.length,1);
 assert.equal(calls[0].options.body.target,'book::chapter.tex:3-3','the span is still the hunk');
 // `.length`, not `deepEqual([])`: an empty array the vm realm created is not
 // `deepStrictEqual` to one this realm created, and the claim is about the count.
 assert.equal(calls[0].options.body.expected.length,0,'a block whose span is not this hunk publishes no token for it');
 assert.equal(addressed(context,calls[0].options.body).before,'The packaged editor saves this change.','and `before` is still the byte guard over that hunk');
});

for(const [history_kind,path] of [['section','/authoring/section-change'],['block','/authoring/block-change']])test(`explicit ${history_kind} history uses its structural Undo endpoint`,async()=>{
 const calls=[],change=history_kind==='section'?{history_kind,undo:{operation:'undo-create'},redo:null}:{history_kind,edits:[{file:'chapter.tex',before:'Before',after:'After'}],placement:null};
 const context={S:{corpus:'book'},E:{dirty:false},P:new Map(),savedEditHistory:{undo:[change],redo:[],external:new Set(),pending:[],busy:false},URLSearchParams,restoreEditHistory:()=>true,persistEditHistory(){},emit(){},clearObjectSelection(){},findObject(){return null;},selectObject(){},window:{walk:{refresh:async()=>{}}},store:{fetchJSON:async(request,options)=>{calls.push({path:request,options});return {ok:true,undo:{operation:'redo-create'}};}}};
 Object.assign(context,{sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError});context.S ||= {corpus:"book"};vm.createContext(context);vm.runInContext(body+';this.undo=undoEditorChange;',context);await context.undo();assert.equal(calls.length,1);assert.equal(calls[0].path,path);
});


function retryFixture(result,second){const sent=[],events=[],witness={schema_version:'laplace.rewrite-retry/1',pending_id:'FB-first',intent_sha256:'a'.repeat(64)},first=result||{pending:true,record:{id:'FB-first',kind:'pending-rewrite'},receipt:{row_id:'FB-first',rewrite_retry:witness,refused:{needed:{expected:['served-token']}}}},ack=second||{applied:{file:'main.tex'},record:{id:'FB-applied'},receipt:{retry_settlement:{status:'RESOLVED',pending_id:'FB-first'}}};
 const context={REQUEST_FIELDS:['expected','verb','concept','target','by'],ADJUDICATE:'/review/adjudicate',emit:(...args)=>events.push(args),appliedOf:value=>!!value?.applied,store:{fetchJSON:async(path,options)=>{sent.push(structuredClone(options.body));if(sent.length===1)return first;if(ack instanceof Error)throw ack;return ack;}}};Object.assign(context,{sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError});context.S ||= {corpus:"book"};vm.createContext(context);vm.runInContext(sliceA+sliceB+';this.retry=retrySaveOnce;',context);return {context,sent,events,first,ack,witness};}
test('actual one served retry carries only exact first pending witness and returns successful effect ack',async()=>{const f=retryFixture(),request={verb:'change',concept:'prose@paragraph',target:'book::main.tex:2-2',by:'author',expected:['old-token'],payload:{before_content:'Original',after:'Revised',note:'Keep note'}};const result=await f.context.retry(request);assert.equal(result,f.ack);assert.equal(f.sent.length,2);assert.deepEqual(f.sent[1].payload.rewrite_retry,f.witness);assert.deepEqual(f.sent[1].expected,['served-token']);assert.equal(f.sent[1].payload.before_content,'Original');assert.equal(f.sent[1].payload.after,'Revised');assert.equal(request.payload.rewrite_retry,undefined);});
test('malformed first record linkage refuses retry and failed retry retains original pending',async()=>{const f=retryFixture({pending:true,record:{id:'OTHER'},receipt:{row_id:'FB-first',rewrite_retry:{pending_id:'FB-first'},refused:{needed:{expected:['new']}}}});assert.equal(await f.context.retry({payload:{},expected:['old']}),f.first);assert.equal(f.sent.length,1);const failed=retryFixture(null,new Error('offline'));assert.equal(await failed.context.retry({payload:{},expected:['old']}),failed.first);assert.equal(failed.sent.length,2);});
test('retry settlement warning preserves exact applied ack without a third effect call',async()=>{const ack={applied:{file:'main.tex'},record:{id:'FB-new'},receipt:{retry_warning:'Applied; FB-first remains unresolved. Do not repeat effect.'}},f=retryFixture(null,ack);assert.equal(await f.context.retry({payload:{},expected:['old']}),ack);assert.equal(f.sent.length,2);assert.match(f.events.at(-1)[1].text,/FB-first/);});


test('final actual Undo status retains settlement warning after successful source/history transition',async()=>{
 const events=[],change=captureSourceChange('Head\nRevised\nTail',{file:'chapter.tex',line_start:2,before:'Original',after:'Revised'}),context={S:{corpus:'book',blocks:[]},C:{actor:'author'},E:{dirty:false},P:new Map(),savedEditHistory:{undo:[change],redo:[],external:new Set(),pending:[],busy:false},URLSearchParams,restoreEditHistory:()=>true,persistEditHistory(){},emit:(...args)=>events.push(args),readEditorSource:async()=> 'Head\nRevised\nTail',historySpan,ADJUDICATE:'/review/adjudicate',appliedOf:()=>true,window:{walk:{refresh:async()=>{}}},store:{fetchJSON:async()=>({applied:{file:'chapter.tex'},receipt:{retry_warning:'Source applied; pending FB-first unresolved.'}})}};
 Object.assign(context,{sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError});context.S ||= {corpus:"book"};vm.createContext(context);vm.runInContext(body+PRODUCERS+';this.undo=undoEditorChange;',context);await context.undo();assert.equal(context.savedEditHistory.undo.length,0);assert.equal(context.savedEditHistory.redo.length,1);assert.match(events.at(-1)[1].text,/Change undone.*FB-first unresolved/);
});


test('visual source request keeps the observed selected edition and refuses a retry replacing it',()=>{
 const code=source.slice(source.indexOf('const REQUEST_FIELDS ='),source.indexOf('/** Set one payload key'));
 const sandbox={S:{corpus:'book'},D:{sourceObservation:{source_observation:{selection_identity:'edition-original'}}},C:{actor:'author'},scopeFields:value=>value};Object.assign(sandbox,{sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError});vm.createContext(sandbox);vm.runInContext(code+';this.build=sourceRequest;this.retry=withNeeded;',sandbox);
 const original=sandbox.build({file:'main.tex',lineStart:1,lineEnd:1,before:'Old',after:'New'});assert.equal(original.payload.expected_selection,'edition-original');sandbox.D.sourceObservation.source_observation.selection_identity='edition-now';
 assert.equal(sandbox.retry(original,{expected_selection:'edition-now',before_content:'Old'}),null);
 const moved=sandbox.retry(original,{target:'book::main.tex:2-2',payload:{before_content:'Old',expected_selection:'edition-now'}});assert.equal(moved.payload.expected_selection,'edition-original');
 const held=sandbox.build({file:'main.tex',lineStart:1,lineEnd:1,before:'Old',after:'New',expectedSelection:'edition-original'});assert.equal(held.payload.expected_selection,'edition-original');
});

test('actual visual retry consumes owner effect before any served-needed replay',async()=>{
 const {fixtures}=await import('./helpers/source_effect_fixture.mjs');
 for(const name of ['committed','incomplete','partial','rollback','unproved','unchanged_incomplete']){
  const result=structuredClone(fixtures[name].result);
  result.receipt={refused:{needed:{expected:['new-token']}}};
  const f=retryFixture(result);
  const request={payload:{expected_selection:'sha256:'+'b'.repeat(64)},expected:['original-token']};
  if(name==='committed')assert.equal(await f.context.retry(request),result);
  else await assert.rejects(f.context.retry(request),/incomplete|rolled back|unproved/);
  assert.equal(f.sent.length,1);
  assert.deepEqual(request.expected,['original-token']);
 }
});
