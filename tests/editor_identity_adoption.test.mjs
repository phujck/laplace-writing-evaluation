// Sequential editor saves and the draft basis lifecycle (root B6; Sol reviews 2026-10-12).
// The in-place reload adopts the owner's source, spans, pieces AND identity witnesses
// together (`adoptBlockModel`). A draft is an edit OF an explicit basis — raw source, span,
// selection identity, issued tokens — captured when editing begins, carried through park,
// persistence and resume, and moved only on proof: unchanged raw bytes (`readdressDraft`) or
// an acknowledged own postimage. Rendered equality and context placement are never authorization;
// anything unproven is a MOVED draft (wave 14b): his words stand in their paragraph, unsaved, and his explicit save writes them.
// These tests drive the REAL functions sliced from walk.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {emptyParagraphSource,normalizeDraftRows,manuscriptDocumentVersion,manuscriptPresentationVersion,planScopedReload,canRefreshBlockInPlace} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {walkSource,walkDeclarations} from './helpers/walk_source.mjs';
const source=walkSource();
const section=(start,end)=>{const at=source.indexOf(start);assert.ok(at>=0,start);const until=source.indexOf(end,at);assert.ok(until>at,end);return source.slice(at,until);};
const identityCode=walkDeclarations('expectedOf','adoptBlockModel','captureBasis','assignBasis','basisOf','verifyAwaiting','readdressDraft',
 'awaitingUnread','REVIEW_WORDS','MOVED_WORDS','ownParagraph','NOT_SAVED','sayNotSaved','NOT_LOCATED','NOT_LOCATED_LINE','keepPlace');
const faceCode=section('function placeDraft(','/** After a whole re-adopt');
const parkedCode=walkDeclarations('restoreParked');
const snapshotCode=walkDeclarations('snapshotEdit');
const parkCode=section('function parkEntry(','/** The changed span')+walkDeclarations('parkEdit');
const clearCode=section('function clearEdit(','/** Esc — the paragraph');
const persistCode=section('function localDraftRows(','function saveParks(');
const commitCode=(source.slice(source.indexOf('async function commitEdit('),source.indexOf('  setPayload(payload,',source.indexOf('async function commitEdit(')))+'return payload;}').replace('async function commitEdit(','async function commitEditReal(');
const flipCode=section('function settleFlipContinuation(','  const s = F.baseSource||srcOf(b);')+'return "sent";}';
const loadCode=section('function loadParks(','/** Moving away PARKS');
const batchCode=walkDeclarations('commitAll');
const normalizeCode=section('function normalizeDoc(','async function loadDoc(');
const reloadCode=walkDeclarations('fetchDocForBlock','mergeHeldSections','adoptWitnesses','_reloadBlock');
const T=(file,line,digest)=>`rev:prose:book::${file}:${line}-${line}:${digest}`;
const model=(id,tex,line,digest,extra={})=>({id,kind:'para',tex,src:{file:'chapter.tex',repo_file:'paper/chapter.tex',line_start:line,line_end:line},expected:[T('chapter.tex',line,digest)],pieces:[{o_start:0,o_end:tex.length,kind:'text'}],presentation_only:false,math:'',equation_labels:[],number:'',env:'',custom_kind:'',presentation:{},preview_image:'',title_prefix:'',title_suffix:'',theorem_label:'',theorem_optional_title:false,theorem_numbered:false,title_pieces:null,tail_pieces:null,tail:'',items:null,rows:null,ordered:false,image:'',images:[],caption:'',caption_separate:false,caption_of:null,caption_pieces:null,title:'',text:tex,level:'',suggestion:false,spec_id:'',spec_ids:undefined,source_section:'',restructure_preview:null,label:'',labels:[],...extra});

function editor({blocks,faces,selection='sel-1',reload=false,fetchJSON=null}){
  // One canvas: blocks with rendered faces, the editing state, and doubles for the DOM-only
  // neighbours. `faces` is the rendered text per block; a block "re-render" is the test
  // setting its face to the render of its current tex.
  const E={blockId:'',pristine:'',tex:'',src:null,expectedSelection:undefined,expected:null,awaiting:null,supersedes:null,moved:false,place:null,dirty:false,timer:0,committing:false,composing:false,scope:'',selAnchor:null},P=new Map(),cards=[],applied=[],events=[],inserted=[],requests=[],notes=[],storage=new Map();
  const F={baseTex:null,baseSource:null,baseExpected:null,awaiting:null,blockId:'',ta:null,noteEl:null,saveBtn:null,saving:false};
  const D={sourceObservation:{source_observation:{selection_identity:selection}}};
  let range=null;
  const bindings={INFLIGHT:new Set(),QUEUE:{why:''},E,P,D,F,S:{blocks},blockById:new Map(blocks.map(b=>[b.id,b])),C:{actor:'author'},cardNote:null,RELOAD_INFLIGHT:null,pendingPresentationSplits:new Map(),crypto:{randomUUID:()=>'draft-'+(P.size+1)},OWNER_READ:{seq:1},requests,
    setFlipNote:(words,tone)=>notes.push([words,tone]),window:{localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)}},PARK_KEY:()=>'walk-parks:book',normalizeDraftRows,storageRecovered(){},storageFailure(){},renderBand(){},paintDeposits(){},bankCardComment:async()=>null,flipBlock:()=>false,
    hostText:host=>faces.get(host.block.id),srcOf:b=>({file:b.src.file,lineStart:b.src.line_start,lineEnd:b.src.line_end}),
    applyFace:(b,entry)=>{applied.push(b.id);faces.set(b.id,entry.text);return true;},
    nodeAt:(host,at)=>({node:host,off:at}),
    document:{createRange:()=>{range={};return {setStart(node,off){range.start=off;},setEnd(node,off){range.end=off;},deleteContents(){},insertNode(node){const id=node.block;const fresh=faces.get(id);faces.set(id,fresh.slice(0,range.start)+node.data+fresh.slice(range.end));inserted.push(node.data);}};},createTextNode:text=>({data:text,get block(){return currentBlock;}}),getSelection:()=>null},
    showCard:(b,words,tone)=>cards.push({id:b.id,words,tone}),paintParked(){},setEditScope(){},autosize(){},clearTimeout(){},emit:(...args)=>events.push(args),
    matchHeldDraft:(entry,rows)=>rows.find(row=>row.file===entry.src?.file&&row.line_start===entry.src?.lineStart)?.id||null,
    taggedParagraph:()=>false,setPayload:(body,key,value)=>{body[key]=value;return body;},sourceForRenderedRange:(b,start,end)=>faces.get(b.id).slice(start,end),pieceTypeAt:()=>'text',anchorFromPristine:(b,full,start,end)=>({file:b.src.file,lineStart:b.src.line_start,lineEnd:b.src.line_end,blockId:b.id,sectionId:'',quote:full.slice(start,end),tex:b.tex}),
    sourceRequest:parts=>parts,emptyParagraphSource,toSourceRegister:value=>value,rewritePayload:(a,after,note,expected)=>({file:a.file,lineStart:a.lineStart,lineEnd:a.lineEnd,before:a.quote,after,note,expected}),showStructuralOutcome(){},structuralSourceHolds:new Map(),offsetIn:()=>0,paintMarks(){},measure(){},captureFocus:()=>null,restoreFocus(){},
    renderBlockBody:(b)=>{faces.set(b.id,render(b.tex));},askActor(){},
    // the reload flow's neighbours: the owner read double, the whole-adopt double and chrome
    store:{fetchJSON:async(path,options)=>fetchJSON(path,options)},manuscriptDocumentVersion,manuscriptPresentationVersion,planScopedReload,canRefreshBlockInPlace,
    paragraphTransition:null,rememberParagraphCaret(){},editorInsertionPoint:()=>null,blockLabels:()=>[],LK:{facts:{clear(){}}},renderDoc(){},buildSpine(){},rekeyRows(){},paintDeposits(){},checkOrphans(){},editableBlock:()=>true,caretRange:()=>null,refreshProposalView:async()=>{},showStructuralOutcome(){},litNode(){},
    adopt:next=>{bindings.OWNER_READ.seq+=1;for(const sec of next.sections)for(const b of sec.blocks)b.readSeq=bindings.OWNER_READ.seq;bindings.D.sections=next.sections;bindings.D.documentVersion=next.documentVersion;bindings.D.presentationVersion=next.presentationVersion;bindings.D.sourceObservation=next.sourceObservation;bindings.D.sectionIndex=next.sectionIndex||[];bindings.D.sectionWitness=Object.fromEntries(bindings.D.sectionIndex.map(row=>[row.id,row.file_revision]));bindings.D.staleSections=new Set();bindings.S.blocks=next.sections.flatMap(sec=>sec.blocks);bindings.blockById.clear();for(const b of bindings.S.blocks){bindings.blockById.set(b.id,b);const host={block:b,normalize(){},set textContent(value){faces.set(b.id,value);}};b.pieceMap=[{t:'text'}];b.bodyEl=host;b.el={dataset:{},toggleAttribute(){}};faces.set(b.id,render(b.tex));}}};
  let currentBlock='';
  // a plain paragraph's piece map (all text), so a moved draft takes his whole text (walk-drafts.mjs placeDraft)
  for(const b of blocks){const host={block:b,normalize(){},set textContent(value){faces.set(b.id,value);}};Object.defineProperty(host,'id',{get(){return b.id;}});b.bodyEl=host;b.el={dataset:{}};b.readSeq=1;if(!b.pieceMap)b.pieceMap=[{t:'text'}];}
  const render=tex=>tex.replace(/\\emph\{([^}]*)\}/g,'$1').replace(/---/g,'—');
  const names=Object.keys(bindings).join(',');
  const api=new Function('bindings',`const {${names}}=bindings;let parkBaseline=[],parksLoaded=false,docIdentities={},lkPainted='';${identityCode}${faceCode}${parkedCode}${snapshotCode}${parkCode}${clearCode}${persistCode}${commitCode}${flipCode}${loadCode}${batchCode}${reload?normalizeCode+reloadCode:'function normalizeDoc(){}\nasync function _reloadBlock(){}\nfunction adoptWitnesses(){}\nfunction mergeHeldSections(){}'}
    async function commitEdit(why){const payload=await commitEditReal(why);if(!payload)return null;requests.push(payload);clearEdit(blockById.get(E.blockId));return {id:'FB-new-'+requests.length,applied:true,pending:false};}
    return {expectedOf,adoptBlockModel,captureBasis,assignBasis,basisOf,readdressDraft,verifyAwaiting,awaitingUnread,placeDraft,restoreFace,restoreParked,snapshotEdit,parkEdit,clearEdit,commitEdit:commitEditReal,commitAll,localDraftRows,loadParks,settleFlipContinuation,saveFlip,normalizeDoc,_reloadBlock};`)(bindings);
  // the text-node double needs the block whose face is being edited
  const restore=api.restoreFace;api.restoreFace=b=>{currentBlock=b.id;return restore(b);};
  return {...api,E,P,D,F,S:bindings.S,cards,applied,events,inserted,requests,notes,storage,faces,blocks,byId:bindings.blockById,render,OWNER_READ:bindings.OWNER_READ,adopt:bindings.adopt};
}
const basis=entry=>({tex:entry.tex,src:entry.src,expectedSelection:entry.expectedSelection,expected:entry.expected});

test('the adoption seam carries source, spans, pieces and identity witnesses together and leaves local editing state alone',()=>{
  const b={...model('b1','Old prose.',5,'aaa'),el:{},bodyEl:{},pieceMap:[{x:1}],texFace:false,sectionId:'intro'};
  const {adoptBlockModel,expectedOf}=editor({blocks:[],faces:new Map()});
  const n=model('b1','New prose.',6,'bbb');
  adoptBlockModel(b,n);
  assert.equal(b.tex,'New prose.');assert.deepEqual(b.src,n.src);assert.deepEqual(b.pieces,n.pieces);assert.deepEqual(expectedOf(b),[T('chapter.tex',6,'bbb')]);
  assert.deepEqual(b.pieceMap,[{x:1}]);assert.equal(b.sectionId,'intro');assert.ok(b.el&&b.bodyEl);
  adoptBlockModel(b,{...model('b1','Newer.',6,'ccc'),expected:undefined});assert.deepEqual(expectedOf(b),[]);
});

for(const [name,tex1,tex2,tex3] of [['plain text','Charlie original.','Charlie revised once.','Charlie revised twice.'],['typography and inline TeX','Charlie held draft --- keep $x^2$ unsaved.','Charlie held draft --- keep $x^3$ unsaved.','Charlie original --- $x^3$.']])
test(`two clean consecutive edits (${name}) each bank under the basis captured from their current source`,async()=>{
  const faces=new Map([['b1',tex1]]);const ed=editor({blocks:[model('b1',tex1,11,'d1')],faces});const b=ed.byId.get('b1');
  ed.snapshotEdit(b,b.bodyEl);
  assert.deepEqual(basis(ed.E),{tex:tex1,src:{file:'chapter.tex',lineStart:11,lineEnd:11},expectedSelection:'sel-1',expected:[T('chapter.tex',11,'d1')]},'the basis is captured together when editing begins');
  faces.set('b1',tex2);ed.E.dirty=true;
  const first=await ed.commitEdit('explicit-save');assert.deepEqual(first.expected,[T('chapter.tex',11,'d1')]);
  // the door acknowledged the save: the draft clears and the re-read adopts the new source WITH its identity
  ed.clearEdit(b);ed.adoptBlockModel(b,model('b1',tex2,11,'d2'));
  assert.deepEqual(ed.expectedOf(b),[T('chapter.tex',11,'d2')]);
  ed.snapshotEdit(b,b.bodyEl);assert.equal(ed.E.pristine,tex2);assert.equal(ed.E.tex,tex2);assert.deepEqual(ed.E.expected,[T('chapter.tex',11,'d2')]);
  faces.set('b1',tex3);ed.E.dirty=true;
  const second=await ed.commitEdit('explicit-save');assert.deepEqual(second.expected,[T('chapter.tex',11,'d2')]);assert.equal(second.lineStart,11);
});

test('a shifted span re-addresses a held draft only on proof: same raw bytes and same selection identity',()=>{
  const faces=new Map([['b1','First paragraph.'],['b2','Second paragraph.']]);const ed=editor({blocks:[model('b1','First paragraph.',3,'f1'),model('b2','Second paragraph.',5,'s1')],faces});
  const b2=ed.byId.get('b2');ed.snapshotEdit(b2,b2.bodyEl);faces.set('b2','Second paragraph, extended.');ed.E.dirty=true;ed.parkEdit(b2);
  assert.deepEqual(basis(ed.P.get('b2')),{tex:'Second paragraph.',src:{file:'chapter.tex',lineStart:5,lineEnd:5},expectedSelection:'sel-1',expected:[T('chapter.tex',5,'s1')]});
  // the paragraph above grew by one line: b2's bytes are unchanged but its address moved
  ed.adoptBlockModel(b2,model('b2','Second paragraph.',6,'s1-at-6'));faces.set('b2','Second paragraph.');
  ed.restoreFace(b2);
  const held=ed.P.get('b2');assert.deepEqual(held.expected,[T('chapter.tex',6,'s1-at-6')]);assert.equal(held.src.lineStart,6);assert.equal(held.tex,'Second paragraph.');assert.equal(held.review,undefined);
  assert.equal(faces.get('b2'),'Second paragraph, extended.','the parked words are back on the page');
  // the same bytes under a different document selection are not re-addressed
  const other=editor({blocks:[model('b3','Third.',9,'t1')],faces:new Map([['b3','Third.']]),selection:'sel-2'});
  const b3=other.byId.get('b3');other.P.set('b3',{pristine:'Third.',text:'Third, more.',scope:'',src:{file:'chapter.tex',lineStart:9,lineEnd:9},tex:'Third.',expectedSelection:'sel-1',expected:[T('chapter.tex',9,'t1')]});
  assert.equal(other.readdressDraft(other.P.get('b3'),b3),false);
});

test('same-looking external markup cannot re-key a draft: the original authority stands and the draft stands in its paragraph as moved (wave 14b: no hold)',async()=>{
  const faces=new Map([['b1','Alpha original.']]);const ed=editor({blocks:[model('b1','Alpha \\emph{original}.',7,'a1')],faces});const b=ed.byId.get('b1');
  ed.snapshotEdit(b,b.bodyEl);faces.set('b1','Alpha original, with my words.');ed.E.dirty=true;ed.parkEdit(b);
  // the external source becomes `Alpha original.` — a different byte sequence with the same face
  ed.adoptBlockModel(b,model('b1','Alpha original.',7,'ext'));faces.set('b1',ed.render(b.tex));
  ed.restoreFace(b);
  const held=ed.P.get('b1');
  assert.deepEqual(held.expected,[T('chapter.tex',7,'a1')],'the external token is not substituted');assert.equal(held.tex,'Alpha \\emph{original}.');
  assert.equal(held.review,undefined);assert.equal(held.moved,true,'the source moved under the draft: said, never held');
  assert.deepEqual(ed.cards,[],'no card: the status line says it, beside Keep my text and save it');
  assert.equal(faces.get('b1'),'Alpha original, with my words.','his words stand in the paragraph');
  // the opt-in autosave sends nothing for it; his explicit save (wave 14a, ruling 1) sends his text under the
  // draft's own authority, and the owner applies it over the span as it is now
  ed.snapshotEdit(b,b.bodyEl);assert.equal(ed.E.moved,true);ed.E.dirty=true;
  assert.equal(await ed.commitEdit('autosave'),null);
  const kept=await ed.commitEdit('explicit-save');assert.match(kept.after,/with my words/);assert.deepEqual(kept.expected,[T('chapter.tex',7,'a1')]);
  assert.deepEqual(ed.expectedOf(b),[T('chapter.tex',7,'ext')],'the block keeps the owner token; nothing is dropped');
});

test('context placement after an external change keeps the old authority; the draft is moved and his explicit save sends it',async()=>{
  const faces=new Map([['b1','The quick brown fox jumps over the lazy dog.']]);const ed=editor({blocks:[model('b1','The quick brown fox jumps over the lazy dog.',5,'q1')],faces});const b=ed.byId.get('b1');
  ed.snapshotEdit(b,b.bodyEl);faces.set('b1','The quick brown fox leaps over the lazy dog.');ed.E.dirty=true;ed.parkEdit(b);
  // someone else appended a sentence: the pristine neighbourhood still locates the changed span
  ed.adoptBlockModel(b,model('b1','The quick brown fox jumps over the lazy dog. Added by someone else.',5,'ext'));faces.set('b1',b.tex);
  b.pieceMap=[{t:'text'},{t:'math'}];   // an island in the paragraph: his change is placed by its context, not by retyping the face
  ed.restoreFace(b);
  assert.deepEqual(ed.inserted,['lea'],'the changed span (the prefix/suffix diff of jumps→leaps) was re-placed by context');
  assert.equal(faces.get('b1'),'The quick brown fox leaps over the lazy dog. Added by someone else.');
  const held=ed.P.get('b1');assert.equal(held.moved,true);assert.equal(held.review,undefined);assert.deepEqual(held.expected,[T('chapter.tex',5,'q1')]);assert.equal(held.tex,'The quick brown fox jumps over the lazy dog.');
  ed.snapshotEdit(b,b.bodyEl);ed.E.dirty=true;assert.equal(await ed.commitEdit('autosave'),null,'placement does not authorize the autosave');
  const kept=await ed.commitEdit('explicit-save');assert.deepEqual(kept.expected,[T('chapter.tex',5,'q1')],'his explicit save sends under the old authority (wave 14a, ruling 1)');
});

test('an acknowledged own save advances a continued draft only onto its verified postimage; after an intervening change the later words stand as a moved draft',()=>{
  const continued=(adopted)=>{
    const faces=new Map([['b1','Charlie original.']]);const ed=editor({blocks:[model('b1','Charlie original.',11,'d1')],faces});const b=ed.byId.get('b1');
    // the save of "Charlie revised." was acknowledged while the author kept typing; the
    // continued park's basis is the acknowledged postimage with no issued token yet
    ed.P.set('b1',{pristine:'Charlie revised.',text:'Charlie revised more.',scope:'',src:{file:'chapter.tex',lineStart:11,lineEnd:11},tex:'Charlie revised.',expectedSelection:'sel-1',expected:[]});
    ed.E.blockId='b1';ed.E.pristine='Charlie revised.';Object.assign(ed.E,{tex:'Charlie revised.',src:{file:'chapter.tex',lineStart:11,lineEnd:11},expectedSelection:'sel-1',expected:[]});ed.E.dirty=true;
    ed.adoptBlockModel(b,model('b1',adopted,11,'d2'));faces.set('b1',adopted);
    ed.restoreFace(b);return ed;};
  const verified=continued('Charlie revised.');
  assert.deepEqual(verified.P.get('b1').expected,[T('chapter.tex',11,'d2')]);assert.deepEqual(verified.E.expected,[T('chapter.tex',11,'d2')]);assert.equal(!!verified.P.get('b1').moved,false);
  assert.equal(verified.faces.get('b1'),'Charlie revised more.','the later typing is preserved over the saved face');
  const intervened=continued('Charlie revised by someone else.');
  assert.deepEqual(intervened.P.get('b1').expected,[],'no token is borrowed for a postimage the owner no longer holds');assert.equal(intervened.P.get('b1').moved,true);assert.equal(intervened.E.moved,true);
  assert.equal(intervened.P.get('b1').text,'Charlie revised more.','the later words are kept');
});

test('the basis survives park, persistence and resume exactly',()=>{
  const faces=new Map([['b1','Alpha \\emph{original}.']]);const ed=editor({blocks:[model('b1','Alpha \\emph{original}.',7,'a1')],faces});const b=ed.byId.get('b1');
  ed.snapshotEdit(b,b.bodyEl);faces.set('b1','Alpha original, edited.');ed.E.dirty=true;ed.parkEdit(b);
  const rows=normalizeDraftRows(JSON.parse(JSON.stringify(ed.localDraftRows())));
  const [[id,row]]=rows;assert.equal(id,'b1');
  assert.deepEqual(basis(row),{tex:'Alpha \\emph{original}.',src:{file:'chapter.tex',lineStart:7,lineEnd:7},expectedSelection:'sel-1',expected:[T('chapter.tex',7,'a1')]});assert.equal(row.moved,false);assert.equal(row.place,null);assert.equal('review' in row,false,'no review field is written');
  // a fresh canvas loads the persisted park and resumes editing against the stored basis
  const again=editor({blocks:[model('b1','Alpha \\emph{original}.',7,'a1')],faces:new Map([['b1','Alpha original.']])});
  again.P.set(id,row);again.restoreParked();
  assert.ok(!again.P.get('b1').moved,'unchanged bytes: an ordinary draft');
  again.snapshotEdit(again.byId.get('b1'),again.byId.get('b1').bodyEl);
  assert.deepEqual(basis(again.E),basis(row));assert.equal(again.E.pristine,'Alpha \\emph{original}.');
});

test('a draft from before the basis was stored stands in its paragraph as moved and never sends a current token (wave 14b: no hold, no reconciliation step)',async()=>{
  const faces=new Map([['b1','Charlie held draft — keep this unsaved.']]);const ed=editor({blocks:[model('b1','Charlie held draft --- keep this unsaved.',11,'c1')],faces});const b=ed.byId.get('b1');
  // the shape an older canvas persisted: words, pristine, span and tex, no expected
  ed.P.set('b1',{pristine:'Charlie held draft — keep this unsaved.',text:'Charlie original.',scope:'',src:{file:'chapter.tex',lineStart:11,lineEnd:11},tex:'Charlie held draft --- keep this unsaved.'});
  ed.restoreParked();
  const held=ed.P.get('b1');assert.equal(held.moved,true);assert.equal(held.review,undefined);assert.equal(ed.basisOf(held),null);assert.deepEqual(ed.cards,[]);
  assert.equal(faces.get('b1'),'Charlie original.','his words stand in the paragraph');
  ed.snapshotEdit(b,b.bodyEl);ed.E.dirty=true;
  assert.equal(await ed.commitEdit('autosave'),null,'the autosave makes no request for a moved draft');
  const kept=await ed.commitEdit('explicit-save');assert.deepEqual(kept.expected,[],'his explicit save sends no current token it was not typed against');
  assert.equal(kept.lineStart,11);assert.match(kept.after,/original/,'his words, over the span as it is now');
});

test('a saved postimage awaiting its read-back is never writable: failed reload, autosave, deletion, partial adoption and external reversion all refuse; only a delivering read verifies it',async()=>{
  const faces=new Map([['b1','Charlie original.'],['b2','Other.']]);const ed=editor({blocks:[model('b1','Charlie original.',11,'d1'),model('b2','Other.',13,'o1')],faces});const b=ed.byId.get('b1');
  // the own save of "Charlie revised." was acknowledged while the author kept typing, and the reload failed:
  // the block still holds the pre-save source and tokens; the draft's basis is the postimage, awaiting
  const awaiting={postimage:'Charlie revised.',file:'chapter.tex',lineStart:11,selection:'sel-1',seq:ed.OWNER_READ.seq};
  const park={pristine:'Charlie revised.',text:'Charlie revised more.',scope:'',src:{file:'chapter.tex',lineStart:11,lineEnd:11},tex:'Charlie revised.',expectedSelection:'sel-1',expected:null,awaiting};
  ed.P.set('b1',{...park});ed.E.blockId='b1';ed.E.pristine='Charlie revised.';ed.assignBasis(ed.E,park);ed.E.dirty=true;
  assert.equal(ed.E.expected,null,'no issued tokens');
  faces.set('b1','Charlie revised more.');
  assert.equal(await ed.commitEdit('autosave'),null);assert.deepEqual(ed.requests,[]);assert.ok(ed.P.get('b1').awaiting);assert.equal(ed.P.get('b1').review,undefined);
  // deleting the paragraph through the empty-paragraph path sends nothing either (own canvas: the refused deletion parks an empty face)
  {const del=editor({blocks:[model('b1','Charlie original.',11,'d1')],faces:new Map([['b1','Charlie revised more.']])});del.P.set('b1',{...park});
   del.snapshotEdit(del.byId.get('b1'),del.byId.get('b1').bodyEl);assert.ok(del.E.awaiting);del.faces.set('b1','');del.E.dirty=true;
   assert.equal(await del.commitEdit('autosave'),null);assert.deepEqual(del.requests,[]);assert.ok(del.P.get('b1').awaiting);}
  // partial adoption: a read delivered another block only; this one keeps waiting, with no review and no reconciliation yet
  ed.OWNER_READ.seq+=1;ed.adoptBlockModel(ed.byId.get('b2'),model('b2','Other, changed.',13,'o2'));
  faces.set('b1','Charlie revised more.');ed.restoreFace(b);assert.ok(ed.P.get('b1').awaiting);assert.equal(!!ed.P.get('b1').moved,false,'nothing newer than the save has been read for this paragraph');
  // an external reversion to the original source, delivered by a read: the draft is moved, its words kept, no token borrowed
  ed.OWNER_READ.seq+=1;ed.adoptBlockModel(b,model('b1','Charlie original.',11,'d1-again'));faces.set('b1','Charlie original.');
  ed.restoreFace(b);
  assert.equal(ed.P.get('b1').moved,true);assert.equal(ed.P.get('b1').awaiting,null);assert.equal(ed.P.get('b1').expected,null);assert.equal(ed.P.get('b1').text,'Charlie revised more.','the later words are kept');
  ed.snapshotEdit(b,b.bodyEl);faces.set('b1','Charlie revised more.');ed.E.dirty=true;assert.equal(await ed.commitEdit('autosave'),null);assert.deepEqual(ed.requests,[]);
  assert.match((await ed.commitEdit('explicit-save')).after,/more/,'his explicit save sends his words (wave 14a, ruling 1)');
  // the positive path: a delivering read holds exactly the postimage, same file and selection, with issued tokens
  const ok=editor({blocks:[model('b1','Charlie original.',11,'d1')],faces:new Map([['b1','Charlie original.']])});const ob=ok.byId.get('b1');
  ok.P.set('b1',{...park,awaiting:{...awaiting,seq:ok.OWNER_READ.seq}});ok.E.blockId='b1';ok.E.pristine='Charlie revised.';ok.assignBasis(ok.E,ok.P.get('b1'));ok.E.dirty=true;
  ob.tex='Charlie revised.';assert.equal(ok.verifyAwaiting(ok.P.get('b1'),ob),false,'a locally assigned source is not a read');
  ok.OWNER_READ.seq+=1;ok.adoptBlockModel(ob,model('b1','Charlie revised.',11,'d2'));ok.faces.set('b1','Charlie revised.');ok.restoreFace(ob);
  assert.equal(ok.P.get('b1').awaiting,null);assert.deepEqual(ok.P.get('b1').expected,[T('chapter.tex',11,'d2')]);assert.deepEqual(ok.E.expected,[T('chapter.tex',11,'d2')]);assert.equal(ok.faces.get('b1'),'Charlie revised more.');
  ok.E.dirty=true;const payload=await ok.commitEdit('explicit-save');assert.deepEqual(payload.expected,[T('chapter.tex',11,'d2')]);
});

test('an awaiting draft stays awaiting through park, persistence and restore, and verifies only against the first delivering read of the next session',()=>{
  const ed=editor({blocks:[model('b1','Charlie original.',11,'d1')],faces:new Map([['b1','Charlie revised more.']])});const b=ed.byId.get('b1');
  const awaiting={postimage:'Charlie revised.',file:'chapter.tex',lineStart:11,selection:'sel-1',seq:ed.OWNER_READ.seq};
  ed.E.blockId='b1';ed.E.pristine='Charlie revised.';ed.assignBasis(ed.E,{tex:'Charlie revised.',src:{file:'chapter.tex',lineStart:11,lineEnd:11},expectedSelection:'sel-1',expected:null,awaiting});ed.E.dirty=true;
  ed.parkEdit(b);assert.deepEqual(ed.P.get('b1').awaiting,awaiting);assert.equal(ed.P.get('b1').expected,null);
  const rows=JSON.parse(JSON.stringify(ed.localDraftRows()));assert.equal(rows[0][1].awaiting.seq,undefined,'no read ordinal is persisted');assert.equal(rows[0][1].awaiting.postimage,'Charlie revised.');
  // next session, the initial read holds the postimage: verified against that read
  const next=editor({blocks:[model('b1','Charlie revised.',11,'d2')],faces:new Map([['b1','Charlie revised.']])});
  next.storage.set('walk-parks:book',JSON.stringify(rows));next.loadParks();
  assert.equal(next.P.get('b1').awaiting,null);assert.deepEqual(next.P.get('b1').expected,[T('chapter.tex',11,'d2')]);assert.equal(next.faces.get('b1'),'Charlie revised more.');
  // next session, the initial read holds something else: a moved draft in its paragraph, no token borrowed
  const other=editor({blocks:[model('b1','Charlie original.',11,'d1')],faces:new Map([['b1','Charlie original.']])});
  other.storage.set('walk-parks:book',JSON.stringify(rows));other.loadParks();
  assert.equal(other.P.get('b1').moved,true);assert.equal(other.P.get('b1').awaiting,null);assert.equal(other.P.get('b1').expected,null);assert.equal(other.P.get('b1').text,'Charlie revised more.');
});

test('the flip continuation sends nothing until a delivering read verifies its postimage, and never without issued tokens',async()=>{
  const ed=editor({blocks:[model('b1','Charlie original.',11,'d1')],faces:new Map([['b1','Charlie original.']])});const b=ed.byId.get('b1');
  const awaiting={postimage:'Charlie revised.',file:'chapter.tex',lineStart:11,selection:'sel-1',seq:ed.OWNER_READ.seq};
  assert.equal(ed.settleFlipContinuation(b,awaiting),null,'no read since the save');
  b.tex='Charlie revised.';assert.equal(ed.settleFlipContinuation(b,awaiting),null,'a locally assigned tex is not a read');
  ed.OWNER_READ.seq+=1;ed.adoptBlockModel(b,model('b1','Charlie original.',11,'d1-again'));assert.equal(ed.settleFlipContinuation(b,awaiting),null,'an external reversion is not the postimage');
  ed.adoptBlockModel(b,model('b1','Charlie revised.',11,'d2'));assert.deepEqual(ed.settleFlipContinuation(b,awaiting),[T('chapter.tex',11,'d2')]);
  ed.D.sourceObservation.source_observation.selection_identity='sel-2';assert.equal(ed.settleFlipContinuation(b,awaiting),null,'another selection identity is not the same authority');ed.D.sourceObservation.source_observation.selection_identity='sel-1';
  Object.assign(ed.F,{blockId:'b1',ta:{value:'Charlie revised again.'},awaiting,baseExpected:null,saveBtn:{disabled:false}});
  assert.equal(await ed.saveFlip(),null);assert.equal(ed.F.saveBtn.disabled,true);assert.match(ed.notes.at(-1)[0],/not read the saved source back/);
  Object.assign(ed.F,{awaiting:null,baseExpected:[]});assert.equal(await ed.saveFlip(),null);assert.match(ed.notes.at(-1)[0],/no identity the read published/);
  Object.assign(ed.F,{baseExpected:[T('chapter.tex',11,'d2')]});assert.equal(await ed.saveFlip(),'sent');
});

test("Charlie's exact pending shape: placed in its paragraph as moved and skipped by the batch while its pending record stays recorded",async()=>{
  const faces=new Map([['b1','Charlie held draft — keep this unsaved during the external-change check.']]);
  const ed=editor({blocks:[model('b1','Charlie held draft --- keep this unsaved during the external-change check.',11,'c1')],faces});
  ed.P.set('b1',{pristine:'Charlie held draft — keep this unsaved during the external-change check.',text:'Charlie original.',scope:'',src:{file:'chapter.tex',lineStart:11,lineEnd:11},tex:'Charlie held draft --- keep this unsaved during the external-change check.',draft_id:'draft-charlie',pendingRow:'FB-20261012-202510-shared-read-charlie',text_at_bank:'Charlie original.'});
  ed.restoreParked();
  assert.equal(ed.P.get('b1').moved,true);assert.equal(ed.P.get('b1').review,undefined);assert.equal(faces.get('b1'),'Charlie original.');
  let batch=await ed.commitAll();
  assert.deepEqual(ed.requests,[]);assert.equal(batch.applied.length,0);assert.equal(batch.retained_pending.length,1);assert.match(batch.message,/pending recorded edit remains unapplied/);
  // a draft an earlier build re-based onto a pending record (`supersedes`, persisted by the base client) saves
  // as a new attempt, and the pending record stays recorded until he retires it
  const again=editor({blocks:[model('b1','Charlie held draft --- keep this unsaved during the external-change check.',11,'c1')],faces:new Map([['b1','Charlie held draft — keep this unsaved during the external-change check.']])});
  again.P.set('b1',{pristine:'Charlie held draft — keep this unsaved during the external-change check.',text:'Charlie original.',scope:'',src:{file:'chapter.tex',lineStart:11,lineEnd:11},tex:'Charlie held draft --- keep this unsaved during the external-change check.',expectedSelection:'sel-1',expected:[T('chapter.tex',11,'c1')],draft_id:'draft-charlie',supersedes:{pendingRow:'FB-20261012-202510-shared-read-charlie',text_at_bank:'Charlie original.'}});
  again.restoreParked();
  batch=await again.commitAll();
  assert.equal(again.requests.length,1);assert.deepEqual(again.requests[0].expected,[T('chapter.tex',11,'c1')]);assert.equal(batch.applied.length,1);assert.equal(again.P.size,0);
  assert.deepEqual(batch.superseded,[{block_id:'b1',file:'chapter.tex',line_start:11,line_end:11,id:'FB-20261012-202510-shared-read-charlie',applied_id:'FB-new-1'}]);
  assert.match(batch.message,/Saved 1 edit/);assert.match(batch.message,/earlier pending record FB-20261012-202510-shared-read-charlie remains recorded; verify the new result FB-new-1, then retire it explicitly/);
});

// The owner's raw document shapes, as `/walk/doc` delivers them.
const rawBlock=(id,tex,line,digest)=>({id,kind:'para',tex,src:{file:'chapter.tex',repo_file:'paper/chapter.tex',line_start:line,line_end:line},expected:[T('chapter.tex',line,digest)],pieces:[{o_start:0,o_end:tex.length,kind:'text'}]});
const rawDoc=({sections,index,selected=null,revision})=>({ok:true,corpus:'book',title:'Book',project:'book',macros:{},refs:{},citations:{},citation_targets:[],identities:{},presentation_revision:'p1',current_revision:revision,source_observation:{selection_identity:'sel-1'},section_index:index,...(selected?{partial:true,selected_sections:selected}:{}),sections});
const whole=()=>rawDoc({revision:'cur1',index:[{id:'secA',file:'chapter.tex',blocks:1,file_revision:'rA1'},{id:'secB',file:'chapter.tex',blocks:1,file_revision:'rB1'}],
  sections:[{id:'secA',title:'A',file:'chapter.tex',blocks:[rawBlock('A','Alpha.',3,'a1')]},{id:'secB',title:'B',file:'chapter.tex',blocks:[rawBlock('B','Charlie original.',11,'b1')]}]});

test('actual _reloadBlock: a partial response delivering A stamps A only; an awaiting B stays unread (not moved) until a response delivers B',async()=>{
  const reads=[];let answer=null;
  const ed=editor({blocks:[],faces:new Map(),reload:true,fetchJSON:async(path,options)=>{reads.push(options?.params);return answer(options?.params);}});
  ed.adopt(ed.normalizeDoc(whole()));
  const A=ed.byId.get('A'),B=ed.byId.get('B'),seq0=ed.OWNER_READ.seq;assert.equal(A.readSeq,seq0);assert.equal(B.readSeq,seq0);
  // B's own save of "Charlie revised." was acknowledged; the reload after it failed, so B awaits its read-back
  ed.P.set('B',{pristine:'Charlie revised.',text:'Charlie revised more.',scope:'',src:{file:'chapter.tex',lineStart:11,lineEnd:11},tex:'Charlie revised.',expectedSelection:'sel-1',expected:null,awaiting:{postimage:'Charlie revised.',file:'chapter.tex',lineStart:11,selection:'sel-1',seq:ed.OWNER_READ.seq}});
  ed.faces.set('B','Charlie revised more.');
  assert.equal(ed.awaitingUnread(ed.P.get('B'),B),true);
  // An edit in A was saved: the scoped read delivers section A only (B's section is held, witness unchanged)
  answer=params=>{assert.equal(params.sections,'secA','the reload asks for the edited block\'s section');return rawDoc({revision:'cur2',selected:['secA'],index:[{id:'secA',file:'chapter.tex',blocks:1,file_revision:'rA2'},{id:'secB',file:'chapter.tex',blocks:1,file_revision:'rB1'}],sections:[{id:'secA',title:'A',file:'chapter.tex',blocks:[rawBlock('A','Alpha, edited.',3,'a2')]}]});};
  const out=await ed._reloadBlock('A');
  assert.deepEqual(out,{ok:true,whole:false,note:''});assert.equal(reads.length,1,'one scoped read, no whole fallback');
  assert.equal(A.tex,'Alpha, edited.');assert.deepEqual(ed.expectedOf(A),[T('chapter.tex',3,'a2')]);assert.equal(A.readSeq,seq0+1,'the delivered block takes the new witness');
  assert.equal(B.readSeq,seq0,'the held block keeps its previous witness');assert.equal(B.tex,'Charlie original.');assert.deepEqual(ed.expectedOf(B),[T('chapter.tex',11,'b1')]);
  assert.equal(ed.awaitingUnread(ed.P.get('B'),B),true,'B was never delivered, so it is still unread');assert.ok(ed.P.get('B').awaiting);assert.equal(!!ed.P.get('B').moved,false);
  assert.equal(ed.D.sectionWitness.secA,'rA2');assert.equal(ed.D.sectionWitness.secB,'rB1');
  // A later response delivering B with exactly the postimage verifies the awaiting draft against that read
  answer=params=>{assert.equal(params.sections,'secB');return rawDoc({revision:'cur3',selected:['secB'],index:[{id:'secA',file:'chapter.tex',blocks:1,file_revision:'rA2'},{id:'secB',file:'chapter.tex',blocks:1,file_revision:'rB2'}],sections:[{id:'secB',title:'B',file:'chapter.tex',blocks:[rawBlock('B','Charlie revised.',11,'b2')]}]});};
  assert.deepEqual(await ed._reloadBlock('B'),{ok:true,whole:false,note:''});
  assert.equal(B.readSeq,seq0+2);assert.equal(A.readSeq,seq0+1,'A was not in this response');
  assert.equal(ed.P.get('B').awaiting,null);assert.deepEqual(ed.P.get('B').expected,[T('chapter.tex',11,'b2')]);assert.equal(!!ed.P.get('B').moved,false);
  assert.equal(ed.faces.get('B'),'Charlie revised more.','the later typing stands over the read-back source');
});

test('actual _reloadBlock: a response delivering B with other bytes makes the awaiting draft a moved draft instead of verifying it',async()=>{
  let answer=null;const ed=editor({blocks:[],faces:new Map(),reload:true,fetchJSON:async(path,options)=>answer(options?.params)});
  ed.adopt(ed.normalizeDoc(whole()));const B=ed.byId.get('B'),seq0=ed.OWNER_READ.seq;
  ed.P.set('B',{pristine:'Charlie revised.',text:'Charlie revised more.',scope:'',src:{file:'chapter.tex',lineStart:11,lineEnd:11},tex:'Charlie revised.',expectedSelection:'sel-1',expected:null,awaiting:{postimage:'Charlie revised.',file:'chapter.tex',lineStart:11,selection:'sel-1',seq:ed.OWNER_READ.seq}});
  ed.faces.set('B','Charlie revised more.');
  answer=()=>rawDoc({revision:'cur2',selected:['secB'],index:[{id:'secA',file:'chapter.tex',blocks:1,file_revision:'rA1'},{id:'secB',file:'chapter.tex',blocks:1,file_revision:'rB2'}],sections:[{id:'secB',title:'B',file:'chapter.tex',blocks:[rawBlock('B','Charlie original.',11,'b1-again')]}]});
  assert.deepEqual(await ed._reloadBlock('B'),{ok:true,whole:false,note:''});
  assert.equal(B.readSeq,seq0+1);assert.equal(ed.P.get('B').moved,true);assert.equal(ed.P.get('B').awaiting,null);assert.equal(ed.P.get('B').expected,null);assert.equal(ed.P.get('B').text,'Charlie revised more.');
});

test('a moved draft on a plain paragraph takes his whole text, so his explicit save makes the paragraph equal his draft (wave 14b, the record\'s item 2)',async()=>{
  const faces=new Map([['b1','The quick brown fox jumps over the lazy dog.']]);const ed=editor({blocks:[model('b1','The quick brown fox jumps over the lazy dog.',5,'q1')],faces});const b=ed.byId.get('b1');
  ed.snapshotEdit(b,b.bodyEl);faces.set('b1','The quick brown fox leaps over the lazy dog.');ed.E.dirty=true;ed.parkEdit(b);
  ed.adoptBlockModel(b,model('b1','The quick brown fox jumps over the lazy dog. Added by someone else.',5,'ext'));faces.set('b1',b.tex);
  ed.restoreFace(b);
  assert.equal(faces.get('b1'),'The quick brown fox leaps over the lazy dog.','his draft, whole, in its paragraph');
  const held=ed.P.get('b1');assert.equal(held.moved,true);assert.equal(held.pristine,'The quick brown fox jumps over the lazy dog. Added by someone else.','typed against the face it shows now');
  assert.match(ed.events.at(-1)[1].text,/Another writer changed this paragraph while your draft was open; your text is kept\./);assert.equal(ed.events.at(-1)[1].error,true);
  ed.snapshotEdit(b,b.bodyEl);
  const payload=await ed.commitEdit('explicit-save');
  assert.ok('The quick brown fox jumps over the lazy dog. Added by someone else.'.includes(payload.before)&&payload.before.includes('Added by someone else'),'the span it replaces is read from the face it shows now, the other writer\'s sentence included');
  assert.match(payload.after,/leaps/);
});
