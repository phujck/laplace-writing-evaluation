import {sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError} from '../src/laplace/web/static_shared/source-effect.mjs';
import {readFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import test from 'node:test';
import assert from 'node:assert/strict';
import {captureSourceChange,captureApplicationChange,continuedEdit,historyReplacement,historySpan,paragraphSplitInsertion,emptyParagraphSource,referenceCommand,canRefreshBlockInPlace,matchHeldDraft,manuscriptBlockRows,recordedProposalAttention,proposalChangeRequest,proposalReadURL,proposalReadIntent,selectedProposalBody,proposalComparisonAvailable,proposalReviewStatus,commentSourceSelection} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {walkSource,walkDeclarations} from './helpers/walk_source.mjs';
// Owner Python helpers: inside Source.check the staged shell wrapper is read-only, so the admitted interpreter
// (LAPLACE_PYTHON) runs the staged scripts/laplace_python.py launcher with -I -B; elsewhere the supported
// scripts/laplace-python wrapper runs exactly as before.
const LAUNCHER=new URL('../scripts/laplace_python.py',import.meta.url).pathname,WRAPPER=new URL('../scripts/laplace-python',import.meta.url).pathname;
const ownerPython=(args,options={})=>process.env.LAPLACE_PYTHON
  ?execFileSync(process.env.LAPLACE_PYTHON,['-I','-B',LAUNCHER,...args],{encoding:'utf8',...options})
  :execFileSync(WRAPPER,args,{encoding:'utf8',...options});

test('comment source selection maps the actual texttt/math paragraph to owner-qualified raw targets and refuses atoms',()=>{
 const line='The file \\texttt{observations.csv} contains $(x,y) = (0,0)$ and $(1,2)$ only.';
 const pieces=JSON.parse(ownerPython(['-c','import json,sys;from laplace.manuscript.walk import tex_pieces;print(json.dumps(tex_pieces(sys.argv[1])))',line]));
 assert.deepEqual(pieces.map(p=>p.t),['text','code','text','math','text','math','text']);
 // The renderer's map shape: owner pieces drawn in order (math shown here by its TeX run; real KaTeX glyphs are a
 // later browser check). Rendered offsets are measured over that display.
 let at=0;const pieceMap=pieces.map(p=>{const rText=String(p.s||'');const row={t:p.t,oStart:p.o_start,oEnd:p.o_end,rStart:at,rEnd:at+rText.length,rText};at+=rText.length;return row;});
 const display=pieceMap.map(p=>p.rText).join('');
 const owner=(source,selection)=>JSON.parse(ownerPython(['-c','import json,sys\nfrom laplace.pipeline.correction_origin import _target\ntry:print(json.dumps({"target":_target({"source_selection":json.loads(sys.argv[2])},{"source_quote":sys.argv[1]})}))\nexcept ValueError as error:print(json.dumps({"refused":str(error)}))',source,JSON.stringify(selection)]));
 const whole=commentSourceSelection({tex:line,pieceMap,display});
 assert.equal(whole.selection.kind,'whole-block');assert.equal(whole.selection.end,line.length);
 assert.deepEqual(owner(line,whole.selection),{target:line});
 const contains=pieceMap[2],math=pieceMap[3];
 const span=commentSourceSelection({tex:line,pieceMap,display,start:contains.rStart+1,end:math.rEnd});
 assert.equal(span.selection.kind,'piece-span');assert.equal(span.selection.display_quote,'contains (x,y) = (0,0)','the displayed text is kept as an observation, not the source target');
 assert.deepEqual(owner(line,span.selection),{target:'contains $(x,y) = (0,0)$'});
 const inside=commentSourceSelection({tex:line,pieceMap,display,start:contains.rStart+1,end:math.rStart+2});
 assert.equal(inside.refused,'inside-math');assert.ok(!('selection' in inside));assert.deepEqual(inside.choices.map(c=>c.selection.kind),['whole-block']);
 assert.equal(commentSourceSelection({tex:line,pieceMap,display,start:pieceMap[1].rStart+2,end:contains.rEnd}).refused,'inside-piece');
 assert.match(owner(line,{...span.selection,end:math.oStart+2}).refused,/inside a math/,'a tampered target refuses at the owner too');
 const astral='Value \u{1D400} holds here.';
 const astralWhole=commentSourceSelection({tex:astral,pieceMap:null,display:astral});
 assert.equal(astralWhole.selection.end,[...astral].length);assert.notEqual(astralWhole.selection.end,astral.length);
 assert.deepEqual(owner(astral,astralWhole.selection),{target:astral},'code-point offsets agree with the owner');
 assert.equal(commentSourceSelection({tex:astral,pieceMap:[{t:'text',oStart:0,oEnd:astral.length,rStart:0,rEnd:astral.length,rText:astral}],display:astral,start:0,end:5}).refused,'unicode');
 assert.equal(commentSourceSelection({tex:line,pieceMap:null,display,start:2,end:6}).refused,'unmapped');
});

test('manuscript navigation reads source coordinates without touching any paragraph DOM',()=>{
 let reads=0;const blocks=Array.from({length:800},(_,index)=>({id:'b'+index,kind:'para',sectionId:'chapter',src:{file:'chapter.tex',line_start:index+1,line_end:index+1},get bodyEl(){reads++;return {textContent:'Current paragraph '+index};}}));
 const navigation=manuscriptBlockRows(blocks);assert.equal(reads,0);assert.equal(navigation.length,800);assert.equal(navigation[799].line_start,800);assert.ok(!Object.hasOwn(navigation[0],'text'));
 const content=manuscriptBlockRows(blocks,block=>block.bodyEl.textContent);assert.equal(reads,800);assert.equal(content[799].text,'Current paragraph 799');assert.equal(content[0].file,navigation[0].file);
});

test('saved edit undo and redo preserve unrelated new manuscript text',()=>{
  const change=captureSourceChange('Heading\nRevised sentence.\nTail',{file:'chapter.tex',line_start:2,before:'Original sentence.',after:'Revised sentence.'});
  const current='Added introduction.\nHeading\nRevised sentence.\nTail';
  const undone=historyReplacement(current,change);
  assert.equal(undone,'Added introduction.\nHeading\nOriginal sentence.\nTail');
  assert.equal(historyReplacement(undone,change,false),current);
});
test('the undo span is the hunk, and the door\'s own splice of it rebuilds the whole file',()=>{
  // The span is what /review/adjudicate is addressed with, and what the row it banks
  // carries (src/laplace/review_surface.py:1846). One locator answers both, so the
  // span and the replacement can never disagree.
  const door=(text,body)=>{const lines=text.split('\n');return [...lines.slice(0,body.line_start-1),...String(body.after).split('\n'),...lines.slice(body.line_end)].join('\n');};
  const guard=(text,body)=>text.split('\n').slice(body.line_start-1,body.line_end).join('\n');
  const chapter='Chapter\n'+Array.from({length:400},(_,i)=>'Filler line '+i+'.').join('\n')+'\nRevised sentence.\n'+Array.from({length:400},(_,i)=>'More filler '+i+'.').join('\n');
  const change=captureSourceChange(chapter,{file:'chapter.tex',line_start:402,before:'Original sentence.',after:'Revised sentence.'});
  const span=historySpan(chapter,change);
  assert.equal(span.line_start,402);assert.equal(span.line_end,402);
  assert.equal(span.before,'Revised sentence.');assert.equal(span.after,'Original sentence.');
  assert.equal(guard(chapter,span),span.before,'the span is the exact bytes the door will compare');
  assert.equal(door(chapter,span),historyReplacement(chapter,change),'the door\'s splice equals the whole-file replacement');
  assert.ok(span.before.length+span.after.length<chapter.length/200,'the row is the size of the hunk, not of the chapter');
});
test('a multi-line undo span covers exactly the lines it replaces',()=>{
  const current='Heading\nFirst new line.\nSecond new line.\nTail';
  const change=captureSourceChange(current,{file:'chapter.tex',line_start:2,before:'One old line.',after:'First new line.\nSecond new line.'});
  const span=historySpan(current,change);
  assert.equal(span.line_start,2);assert.equal(span.line_end,3);
  assert.equal(span.before,'First new line.\nSecond new line.');assert.equal(span.after,'One old line.');
  assert.equal(historyReplacement(current,change),'Heading\nOne old line.\nTail');
  const back=historySpan('Heading\nOne old line.\nTail',change,false);
  assert.equal(back.line_start,2);assert.equal(back.line_end,2);assert.equal(back.after,'First new line.\nSecond new line.');
});
test('an undo inside a line keeps the whole line as its span and the passage beside it',()=>{
  const current='Heading\nA sentence. Revised clause. Another sentence.\nTail';
  const change=captureSourceChange(current,{file:'chapter.tex',line_start:2,before:'A sentence. Original clause. Another sentence.',after:'A sentence. Revised clause. Another sentence.'});
  const span=historySpan(current,change);
  assert.equal(span.line_start,2);assert.equal(span.line_end,2);
  assert.equal(span.replaced,'A sentence. Revised clause. Another sentence.');
  assert.equal(span.replacement,'A sentence. Original clause. Another sentence.');
});
test('undo refuses a conflicting or ambiguous replacement',()=>{
  const change={before:'old',after:'new',prefix:'Heading\n',suffix:'\nTail'};
  assert.throws(()=>historyReplacement('new plus new',change),/safely locate/);
  assert.throws(()=>historyReplacement('newer wording', {...change,after:'new sentence'}),/safely locate/);
});
test('deleting an entire source range has a reversible anchored insertion',()=>{
  const change=captureSourceChange('Heading\n\nTail',{file:'chapter.tex',line_start:2,before:'Deleted paragraph.',after:''});
  const restored=historyReplacement('Heading\n\nTail',change);
  assert.equal(restored,'Heading\nDeleted paragraph.\nTail');
  assert.equal(historyReplacement(restored,change,false),'Heading\n\nTail');
});
test('reference commands preserve real identity and reject invalid TeX arguments',()=>{
  assert.equal(referenceCommand({type:'equation',key:'eq:closure'}),'\\eqref{eq:closure}');
  assert.equal(referenceCommand({type:'citation',key:'Landauer1961'}),'\\cite{Landauer1961}');
  assert.equal(referenceCommand({type:'figure',key:'fig:example'}),'\\ref{fig:example}');
  assert.throws(()=>referenceCommand({key:'bad}label'}),/invalid label/);
});
test('typing while an earlier save is pending becomes a draft over the saved baseline',()=>{
  assert.deepEqual(continuedEdit('Saved sentence.','Saved sentence. Another thought.'),{
    pristine:'Saved sentence.',text:'Saved sentence. Another thought.'});
  assert.equal(continuedEdit('Saved sentence.','Saved sentence.'),null);
});
test('paragraph split writes a normal empty TeX paragraph only at an edge',()=>{
  assert.deepEqual(paragraphSplitInsertion('Alpha',2),{insert:'\n\n',tail:'pha',empty:false});
  assert.deepEqual(paragraphSplitInsertion('Alpha',5),{insert:'\n\n\\par',tail:'',empty:true});
  assert.deepEqual(paragraphSplitInsertion('Alpha',0),{insert:'\\par\n\n',tail:'Alpha',empty:false});
});


test('Enter before trailing source whitespace still creates an empty paragraph',()=>{
  const split=paragraphSplitInsertion('A sentence. ',11);
  assert.equal(split.empty,true);assert.equal(split.insert,'\n\n\\par');
});


test('typing into empty paragraphs retains leading and trailing paragraph boundaries',()=>{
  assert.equal(emptyParagraphSource('\n\nLater paragraph.'),'\\par\n\nLater paragraph.');
  assert.equal(emptyParagraphSource('\n\n\\par'),'\\par\n\n\\par');
});


test('same-count ordinal IDs cannot retarget old paragraph DOM to different source',()=>{
 const old=[{id:'b1',sectionId:'s',kind:'para',tex:'Final paragraph',src:{file:'main.tex',line_start:17}},{id:'b2',sectionId:'s',kind:'para',tex:'\\par',src:{file:'main.tex',line_start:21}}];
 const next=[{...old[0],tex:'\\par'},{...old[1],tex:'Final paragraph'}];assert.equal(canRefreshBlockInPlace(old,next,'b1'),false);
 assert.equal(canRefreshBlockInPlace(old,old.map(b=>({...b,src:{...b.src,line_start:b.src.line_start+2}})),'b1'),true);
 assert.equal(canRefreshBlockInPlace(old,[{...old[0],tex:'Revised final paragraph'},old[1]],'b1'),true);
});
test('held empty paragraph draft cannot silently attach to another paragraph at its old line',()=>{
 const draft={src:{file:'main.tex',lineStart:17},tex:'\\par',pristine:'\\par',text:'Final paragraph with unsaved typing'};
 const blocks=[{id:'b7',file:'main.tex',line_start:17,tex:'Final paragraph',rendered:'Final paragraph'},{id:'b9',file:'main.tex',line_start:21,tex:'\\par',rendered:''}];assert.equal(matchHeldDraft(draft,blocks),null);
});
test('held drafts relocate only within their source and never guess between repeated passages',()=>{
 const draft={src:{file:'main.tex',lineStart:2},tex:'Original.',pristine:'Original.',text:'Revised.'};
 const blocks=[{id:'foreign',file:'other.tex',line_start:2,tex:'Original.',rendered:'Original.'},{id:'same',file:'main.tex',line_start:4,tex:'Original.',rendered:'Original.'}];assert.equal(matchHeldDraft(draft,blocks),'same');blocks.push({...blocks[1],id:'again',line_start:6});assert.equal(matchHeldDraft(draft,blocks),null);
});


test('changed declared theorem presentation invalidates an unchanged source face',()=>{
 const source=[{id:'paragraph',kind:'para',tex:'Text.'},{id:'theorem',kind:'theorem',tex:'Same theorem source',theorem_label:'Proposition',theorem_optional_title:true,theorem_numbered:true}];
 assert.equal(canRefreshBlockInPlace(source,source,'paragraph'),true);assert.equal(canRefreshBlockInPlace(source,[source[0],{...source[1],theorem_label:'Lemma'}],'paragraph'),false);
});
test('lazy inverses use the immutable postimage and account for earlier multiline edits',()=>{
 const source='Heading\nNew first.\nExtra line.\nBetween\nNew second.\nTail',application={complete:true,receipts:[{record:{anchor:{file:'chapter.tex',lines:[1,5],after:source}}}],edits:[{file:'chapter.tex',line_start:2,line_end:2,before:'Old first.',after:'New first.\nExtra line.'},{file:'chapter.tex',line_start:4,line_end:4,before:'Old second.',after:'New second.'}]};const first=captureApplicationChange(application,0),second=captureApplicationChange(application,1);assert.equal(second.line_start,5);assert.equal(second.require_context,true);assert.ok(!second.prefix.includes('New first.'));const undoneSecond=historyReplacement(source,second),undoneBoth=historyReplacement(undoneSecond,first);assert.equal(undoneBoth,'Heading\nOld first.\nBetween\nOld second.\nTail');assert.equal(historyReplacement(historyReplacement(undoneBoth,first,false),second,false),source);
 assert.equal(captureApplicationChange({...application,receipts:[]},0),null,'current source is not a substitute for missing recorded postimage');
});

test('independent inverses derive global lines from one enclosing canonical anchor',()=>{
 const source='Heading\nNew first.\nExtra line.\nBetween\nNew second.\nTail',anchor='New first.\nExtra line.\nBetween\nNew second.',application={complete:true,receipts:[{row_id:'feedback-1',file:'chapter.tex',lines:[2,4],record:{anchor:{file:'chapter.tex',lines:[2,4],after:anchor}}}],edits:[{file:'chapter.tex',line_start:2,line_end:2,before:'Old first.',after:'New first.\nExtra line.'},{file:'chapter.tex',line_start:4,line_end:4,before:'Old second.',after:'New second.'}]};const first=captureApplicationChange(application,0),second=captureApplicationChange(application,1);assert.equal(first.line_start,2);assert.equal(second.line_start,5);assert.equal(historyReplacement(historyReplacement(source,second),first),'Heading\nOld first.\nBetween\nOld second.\nTail');
});
test('enclosing anchor offsets preserve an earlier multiline deletion',()=>{
 const source='Head\nB\nD\nE2\nTail',anchor='B\nD\nE2',application={complete:true,receipts:[{row_id:'feedback-2',file:'chapter.tex',lines:[2,5],record:{anchor:{file:'chapter.tex',lines:[2,5],after:anchor}}}],edits:[{file:'chapter.tex',line_start:2,line_end:3,before:'B\nC',after:'B'},{file:'chapter.tex',line_start:5,line_end:5,before:'E',after:'E2'}]};const first=captureApplicationChange(application,0),second=captureApplicationChange(application,1);assert.equal(second.line_start,4);assert.equal(historyReplacement(historyReplacement(source,second),first),'Head\nB\nC\nD\nE\nTail');
});
test('a surviving repeated sentence cannot substitute for the original edited location during lazy Undo',()=>{
 const postimage='First section\nSame applied sentence.\nFirst tail\nSecond section\nSame applied sentence.\nSecond tail',application={complete:true,edits:[{file:'chapter.tex',line_start:2,line_end:2,before:'Original first sentence.',after:'Same applied sentence.'}],receipts:[{record:{anchor:{file:'chapter.tex',lines:[1,6],after:postimage}}}]};const change=captureApplicationChange(application,0);assert.ok(change);assert.throws(()=>historyReplacement('Second section\nSame applied sentence.\nSecond tail',change),/recorded context/);
});
test('an enclosing anchor still refuses the same recorded context elsewhere in the file',()=>{
 const p='P'.repeat(200),s='S'.repeat(200),source=['Head','UNIQUE NEW','unique tail',p,'CHANGED',s,'separator',p,'CHANGED',s,'Tail'].join('\n'),anchor=['UNIQUE NEW','unique tail',p,'CHANGED'].join('\n'),application={complete:true,edits:[{file:'chapter.tex',line_start:2,line_end:2,before:'UNIQUE OLD',after:'UNIQUE NEW'},{file:'chapter.tex',line_start:5,line_end:5,before:'TARGET',after:'CHANGED'}],receipts:[{record:{anchor:{file:'chapter.tex',lines:[2,5],after:anchor}}}]};const unique=captureApplicationChange(application,0),repeated=captureApplicationChange(application,1);assert.equal(historyReplacement(source,unique).includes('UNIQUE OLD'),true);assert.ok(repeated);assert.throws(()=>historyReplacement(source,repeated),/recorded context/);
});
test('saved comparison attention uses its affected file and exact application rather than an unrelated reading block',()=>{
 const attention=recordedProposalAttention({turn_id:'WT-two',proposal_state:'applied',edits:[{file:'chapters/two.tex',application_id:'WA-two',status:'accepted'}]});assert.equal(attention.surface,'review');assert.equal(attention.label,'Accepted comparison · two.tex');assert.deepEqual(attention.selection,{files:['chapters/two.tex']});assert.deepEqual(attention.review,{turn_id:'WT-two',application_ids:['WA-two']});assert.equal(attention.node_id,undefined);
 const elsewhere=recordedProposalAttention({turn_id:'WT-original',proposal_state:'applied-elsewhere',edits:[{file:'chapters/two.tex',status:'applied_elsewhere',application_id:'WA-later',fulfilled_elsewhere:[{id:'WA-later',turn_id:'WT-later'}]}]});assert.deepEqual(elsewhere.review,{turn_id:'WT-later',application_ids:['WA-later']});
 const mixed=recordedProposalAttention({turn_id:'WT-original',edits:[{file:'a.tex',application_id:'WA-a',application_turn_id:'WT-a'},{file:'b.tex',application_id:'WA-b',application_turn_id:'WT-b'}]});assert.deepEqual(mixed.review,{turn_id:'WT-original',application_ids:[]},'multiple turns never produce mismatched application IDs');
});


test('fresh-change intent keeps old proof guard and requires canonical source identity before review-first proposal',()=>{
 const request=proposalChangeRequest({edit_id:'EDIT-old',file:'lookup-alias.tex',status:'conflict',lifecycle:'blocked',target_proof:{status:'UNPROVEN'},allowed_actions:['reject','keep-current']},{turnId:'WT-old',version:'sha256:old'});assert.deepEqual(request.selection,{files:['lookup-alias.tex']});assert.match(request.text,/not an author_changes correction/);assert.match(request.text,/canonical file identity returned/);assert.match(request.text,/do not apply either new or old edits/);assert.match(request.text,/report that gap instead of guessing counts/);assert.ok(!request.text.includes('conversation_history'));
});


test('actual owner proposal read handles bind record/version/edit and generic request is copied exactly',async()=>{const data=JSON.parse(await readFile(new URL('./fixtures/proposal-navigation-owner-81a740812.json',import.meta.url),'utf8')),handle=data.summary.edits[0].read_handle,options={project:'fixture',turnId:data.summary.turn_id,version:data.summary.proposal_version,editId:data.summary.edits[0].edit_id};assert.equal(proposalReadURL(handle,options),handle.http.url);assert.throws(()=>proposalReadURL(handle,{...options,version:'sha256:other'}),/changed/);assert.throws(()=>proposalReadURL(handle,{...options,editId:'EDIT-other'}),/changed/);const changed=structuredClone(handle);changed.native_request.payload.record_id='WR-other';assert.throws(()=>proposalReadURL(changed,options),/transports disagree/);assert.ok(proposalReadIntent(handle).includes(JSON.stringify(handle.native_request)));assert.equal(proposalReadURL(data.queue.read_handle,{project:'fixture',queue:true}),data.queue.read_handle.http.url);});


test('selected proposal body keeps only its exact actionable comparison and separate summary navigation',async()=>{const data=JSON.parse(await readFile(new URL('./fixtures/proposal-navigation-owner-81a740812.json',import.meta.url),'utf8')),id=data.edit.edits[0].edit_id,joined=selectedProposalBody(data.summary,data.edit,id);assert.equal(joined.edits.length,1);assert.equal(joined.navigation_edits.length,2);assert.equal(joined.edits[0].before,data.edit.edits[0].before);assert.ok(!Object.hasOwn(joined.navigation_edits[1],'before'));assert.throws(()=>selectedProposalBody(data.summary,{...data.edit,proposal_version:'sha256:other'},id),/identity changed/);});


test('review comparison requires actual before and after; exact raw source supports honest fallback and deletion',()=>{assert.equal(proposalComparisonAvailable({allowed_actions:['accept']}),false);assert.equal(proposalComparisonAvailable({before:'old',after:undefined}),false);assert.equal(proposalComparisonAvailable({before:'old',after:'new'}),true);assert.equal(proposalComparisonAvailable({current_before:'old',after:''}),true);assert.equal(proposalComparisonAvailable({current_blocks:[{kind:'para'}],after_blocks:[{kind:'para'}]}),true);});


test('actual human preview handle reads one rendered edit while generic agent read stays plaintext',async()=>{const data=JSON.parse(await readFile(new URL('./fixtures/proposal-human-preview-owner-41034609f.json',import.meta.url),'utf8')),row=data.summary.edits[0],options={project:data.summary.project,turnId:data.summary.turn_id,version:data.summary.proposal_version,editId:row.edit_id};assert.equal(proposalReadURL(row.preview_read,options),row.preview_read.http.url);assert.equal(new URL(row.preview_read.http.url,'http://localhost').searchParams.get('view'),'preview');assert.equal(row.read_handle.native_request.payload.view,'edit');assert.ok(proposalReadIntent(row.read_handle).includes('"view":"edit"'));const joined=selectedProposalBody(data.summary,data.preview,row.edit_id);assert.equal(joined.edits.length,1);assert.ok(joined.edits[0].after_blocks.length);assert.equal(proposalComparisonAvailable(joined.edits[0]),true);assert.ok(!Object.hasOwn(data.plain_edit.edits[0],'after_blocks'));assert.equal(proposalComparisonAvailable(data.plain_edit.edits[0]),true);assert.throws(()=>proposalReadURL(row.preview_read,{...options,editId:'EDIT-other'}),/changed/);assert.throws(()=>selectedProposalBody(data.summary,{...data.preview,proposal_version:'sha256:changed'},row.edit_id),/identity changed/);assert.throws(()=>selectedProposalBody(data.summary,{...data.preview,validation_basis:{}},row.edit_id),/identity changed/);});

// Exercise the actual TeX link rendering callback under a controlled DOM, not
// text-equality acceptance. Owner URLs retain their qualified namespace.
const walkLinkSource=walkSource();
const linkCode=walkLinkSource.slice(walkLinkSource.indexOf('function manuscriptLink('),walkLinkSource.indexOf('/** One piece of a paragraph.',walkLinkSource.indexOf('function manuscriptLink(')));
const ownerCodec=await import('../src/laplace/web/static_shared/writing-owner-read.mjs');
function linkFixture(){
 const events=[],posted=[],hosts=[],reads=[];
 const node=()=>({isConnected:true,attrs:{},listeners:{},set href(value){this.attrs.href=value;},get href(){return this.attrs.href;},removeAttribute(name){delete this.attrs[name];},addEventListener(name,callback){this.listeners[name]=callback;}});
 const frame={parent:{postMessage:(message,origin)=>posted.push({message,origin})}};
 const build=new Function('artifactHumanTarget','isKnownArtifactReadRoute','ownerHumanTarget','isKnownOwnerReadRoute','el','renderPieces','window','location','emit','store','S','blockById','document',linkCode+'; return manuscriptLink;');
 const render=build((raw,options)=>ownerCodec.artifactHumanTarget(raw,options),(raw,options)=>ownerCodec.isKnownArtifactReadRoute(raw,options),raw=>ownerCodec.ownerHumanTarget(raw,{base:'http://local/walk?corpus=A'}),raw=>ownerCodec.isKnownOwnerReadRoute(raw,{base:'http://local/walk?corpus=A'}),node,()=>{},frame,{origin:'http://local',href:'http://local/walk?corpus=A'},(...args)=>events.push(args),{fetchJSON:async(...args)=>{reads.push(args);throw Error('Unexpected source lookup');}},{corpus:'A'},new Map(),{});
 return {posted,reads,events,render(raw){const host={appendChild:link=>hosts.push(link)};render({t:'href',url:raw,s:'Selected owner'},host);return hosts.at(-1);}};
}
test('TeX native Work/material links use same qualified reading owner and never a file lookup',async()=>{
 const target={owner:'repository',repository:'laplace',path:'src/atlas/store.py'};
 const urls=['/work/state?'+new URLSearchParams({project:'B',view:'detail',id:'WORK-source',limit:'1'}),'/projects/material-references?'+new URLSearchParams({project:'B',view:'preview',target:JSON.stringify(target),limit:'16000'})];
 for(const url of urls){const f=linkFixture(),link=f.render(url);await link.listeners.click({preventDefault(){},stopPropagation(){}});assert.equal(f.reads.length,0);assert.equal(f.posted.length,1);assert.equal(f.posted[0].message.type,'laplace:open-owner-read');assert.equal(f.posted[0].message.url,url);assert.equal(new URL(link.href,'http://local').searchParams.get('corpus')||new URL(link.href,'http://local').searchParams.get('project'),'B');assert.equal(f.posted[0].origin,'http://local');}
});
test('known malformed TeX owner routes remain refused while external links stay external',()=>{
 const f=linkFixture();for(const raw of ['/work/state?project=A&project=B&view=detail&id=W','/work/state?project=B&view=detail','/projects/material-references?project=B&view=preview&target=bad']){const link=f.render(raw);assert.equal(link.href,undefined);assert.equal(link.listeners.click,undefined);assert.match(link.title,/Invalid owner/);}assert.equal(f.reads.length,0);assert.equal(f.posted.length,0);
 const external=f.render('https://elsewhere.example/work/state?project=B&view=detail&id=W');assert.equal(external.href,'https://elsewhere.example/work/state?project=B&view=detail&id=W');assert.equal(external.target,'_blank');
});
test('compatibility URL exports and extracted owner have identical validation identity',async()=>{
 const session=await import('../src/laplace/web/static_shared/workspace-session.mjs');
 for(const name of ['ownerHumanTarget','artifactHumanTarget','conceptHumanTarget'])assert.equal(session[name],ownerCodec[name]);
});

const {proposalDraftKey,proposalDraftBasis,proposalDraftBasisMatches,proposalDecisionAcknowledged}=await import('../src/laplace/web/static_shared/manuscript-editing.mjs');
test('a proposed draft keeps its original opaque owner token across reinspection and candidates',()=>{const edit={edit_id:'EDIT-one',review_token:'old-owner-token'},basis=proposalDraftBasis(edit,'V-one');assert.equal(proposalDraftBasisMatches(basis,edit,'V-one'),true);assert.equal(proposalDraftBasisMatches(basis,{...edit,review_token:'new-owner-token'},'V-one'),false);assert.equal(proposalDraftBasisMatches(basis,edit,'V-two'),false);assert.equal(proposalDraftBasisMatches(null,edit,'V-one'),false);assert.equal(proposalDraftBasisMatches(proposalDraftBasis({...edit,review_token:'new-owner-token'},'V-one'),{...edit,review_token:'new-owner-token'},'V-one'),true);});
const ack=()=>({project:'P',turn_id:'T',proposal_version:'V',edits:[{edit_id:'E',status:'accepted',application_id:'WA-exact',application_turn_id:'T'}],application:{id:'WA-exact',project:'P',turn_id:'T',candidate_version:'V',candidate_edit_ids:['E'],complete:false},remaining:2});
test('exact selected application acknowledgement never transfers acceptance to similar candidates or entire remainder',()=>{const scope={project:'P',turnId:'T',version:'V',editId:'E'},valid=ack();assert.equal(proposalDecisionAcknowledged(valid,scope),true);assert.equal(valid.remaining,2);for(const change of [value=>value.project='Q',value=>value.proposal_version='another',value=>value.edits[0].application_id='another',value=>value.application.candidate_edit_ids=[],value=>value.edits[0].status='superseded',value=>value.application.turn_id='elsewhere',value=>{value.application.turn_id='OTHER';value.edits[0].application_turn_id='OTHER';},value=>value.application.project='OTHER-PROJECT']){const value=ack();change(value);assert.equal(proposalDecisionAcknowledged(value,scope),false);}assert.equal(proposalDecisionAcknowledged(undefined,scope),false);});

const draftWalkSource=walkSource();
const decisionCode=draftWalkSource.slice(draftWalkSource.indexOf('let deciding=false;const decide='),draftWalkSource.indexOf('\n    let confirmation=',draftWalkSource.indexOf('let deciding=false;const decide=')));
function decisionFixture(onDecision,throwStorage=false,overrides={}){const calls=[],events=[],removed=[],ui={draftText:'unsent draft',draftBasis:{review_token:'owner-token'}};const status={textContent:'',classList:{add(){}},setAttribute(){}},buttons={querySelectorAll:()=>[]};const build=new Function('bindings',`const {sourceEffectDisposition,status,options,edit,comparisonReady,proposalActionAllowed,ui,reviewedVersion,data,S,draftKey,legacyDraftKey,buttons,localStorage,emit,proposalDecisionAcknowledged,docEl}=bindings;let saveCombined=null;const updatePermission=()=>{};${decisionCode};return decide;`);const decide=build({sourceEffectDisposition,status,options:{onDecision:typeof onDecision==='function'?async(...args)=>{calls.push(args);return onDecision(ui);}:undefined},edit:{edit_id:'E'},comparisonReady:true,proposalActionAllowed:()=>true,ui,reviewedVersion:'V',data:{turn_id:'T'},S:{corpus:'P'},draftKey:'draft-exact',legacyDraftKey:'legacy',buttons,localStorage:{removeItem:key=>{removed.push(key);if(throwStorage)throw Error('quota');}},emit:(...args)=>events.push(args),proposalDecisionAcknowledged,docEl:{querySelectorAll:()=>[]},...overrides});return {decide,ui,status,calls,events,removed};}
test('actual decision callback retains draft when transport or exact application acknowledgement is absent',async()=>{const unavailable=decisionFixture(null);await unavailable.decide('merge',{merged_after:'unsent draft'});assert.equal(unavailable.ui.draftText,'unsent draft');assert.equal(unavailable.calls.length,0);const ambiguous=decisionFixture(()=>undefined);await ambiguous.decide('merge',{merged_after:'unsent draft'});assert.equal(ambiguous.ui.draftText,'unsent draft');assert.equal(ambiguous.removed.length,0);assert.match(ambiguous.events.at(-1)[1].text,/No exact application acknowledgement/);});
test('actual decision only clears acknowledged submitted version, newer typing survives and cleanup errors never reverse the recorded effect',async()=>{const exact=decisionFixture(()=>ack());await exact.decide('merge',{merged_after:'unsent draft'});assert.equal(exact.ui.draftText,undefined);assert.deepEqual(exact.removed,['draft-exact','draft-exact:basis','legacy']);const newer=decisionFixture(ui=>{ui.draftText='newer unsent typing';return ack();});await newer.decide('merge',{merged_after:'unsent draft'});assert.equal(newer.ui.draftText,'newer unsent typing');assert.equal(newer.removed.length,0);assert.match(newer.events.at(-1)[1].text,/newer proposed draft/);const quota=decisionFixture(()=>ack(),true);await quota.decide('merge',{merged_after:'unsent draft'});assert.equal(quota.ui.draftText,undefined);assert.match(quota.events.find(([kind])=>kind==='editor-status')[1].text,/exact application was recorded/);});

// the proposal decision is the proposals owner's (workspace-proposals.mjs, M5 S2 F1); its services are built from the fixture's bindings
const workspaceDecisionSource=await readFile(new URL('../src/laplace/web/static_shared/workspace-proposals.mjs',import.meta.url),'utf8');
const DECISION_SERVICES='const manuscript={editor:()=>manuscriptEditor,saved,rememberApplication},workState={reload:reloadState},ui={notice},discussion={savedTurn:readSavedTurn,open:()=>{},talk:()=>{}},views={current:()=>"manuscript"},inspect={ownerRead:()=>{},projectArtifact:()=>{}};';
const workspaceDecisionCode=workspaceDecisionSource.slice(workspaceDecisionSource.indexOf('    const decide=async(editId,decision'),workspaceDecisionSource.indexOf('\n    };',workspaceDecisionSource.indexOf('    const decide=async(editId,decision'))+7);
function joinedDecisionFixture(failing){const acknowledged=ack();acknowledged.application.edits=[{edit_id:'E'}];let current=true;const events=[],calls=[];const preview={proposal_version:'V',edits:[{edit_id:'E',allowed_actions:['merge']}],identities:{E:'owner-read-guard'}};const step=name=>{calls.push(name);if(name===failing)throw Error(name+' unavailable');};const bindings={humanOptions:{},sourceEffectDisposition,sourceEffectFromError,manuscriptEditor:null,saved(){},preview,project:'P',turnId:'T',selectedVersion:'V',isCurrent:()=>current,proposalActionAllowed:()=>true,proposalDecisionAcknowledged,walk:{proposalDraftConflict:()=>false,showProposal:()=>step('render'),clearProposal:()=>step('clear'),refresh:async()=>step('document')},api:async(path,payload)=>{calls.push({path,payload});return acknowledged;},projectReview:{settled:async()=>step('sidebar')},refresh:async options=>{assert.deepEqual(options,{afterDecision:true});step('parent-read');return acknowledged;},requestChanges(){},selectEdit:null,inspectBasis(){},inspectCurrentFile(){},readSavedTurn(){},manuscriptSaved(){},title:row=>row.title,rememberApplication:async()=>step('history'),reloadState:async()=>step('state'),notice:(...args)=>events.push(args)};const names=Object.keys(bindings).filter(name=>name!=='preview').join(',');const decide=new Function('bindings',`let preview=bindings.preview;const {${names}}=bindings;${DECISION_SERVICES}${workspaceDecisionCode};return decide;`)(bindings);return {decide,acknowledged,events,calls,setCurrent:value=>current=value};}
test('actual joined workspace returns settled owner ack when each post-effect maintenance step fails',async()=>{for(const step of ['sidebar','parent-read','render','history','document','state']){const f=joinedDecisionFixture(step),result=await f.decide('E','merge',{review_token:'original-owner-token',merged_after:'submitted source'});assert.equal(result,f.acknowledged);assert.equal(f.calls.filter(call=>typeof call==='object').length,1);assert.equal(f.calls.find(call=>typeof call==='object').payload.review_token,'original-owner-token');assert.match(f.events.at(-1)[0],/Application recorded; refresh\/history is unavailable/);assert.match(f.events.at(-1)[0],/do not repeat the effect/);}});
test('late acknowledged decision does not repaint another selected review',async()=>{const f=joinedDecisionFixture();f.setCurrent(false);const result=await f.decide('E','merge',{review_token:'owner-token'});assert.equal(result,f.acknowledged);assert.equal(f.calls.filter(call=>typeof call==='string').length,0);assert.equal(f.events.length,0);});

test('actual joined callback preserves source facts and drafts when application tracking is unproved',async()=>{
 const f=joinedDecisionFixture(),next=f.acknowledged;next.application={complete:false,source_applied:true,application_tracking:{status:'UNPROVED',attempted_id:'WA-unrecorded'},receipts:[{row_id:'FB-exact'}]};next.application_tracking=next.application.application_tracking;next.source_applied=true;next.warning='Source changes applied; tracking unproved. Inspect exact feedback; do not repeat the effect.';next.edits[0].status='conflict';
 const result=await f.decide('E','merge',{review_token:'original-owner-token',merged_after:'submitted source'});assert.equal(result,next);assert.equal(f.calls.filter(call=>typeof call==='object').length,1);assert.deepEqual(f.calls.filter(call=>typeof call==='string'),['render','document']);assert.match(f.events[0][0],/Source changes applied/);assert.equal(f.calls.includes('history'),false);assert.equal(f.calls.includes('sidebar'),false);
 const data={turn_id:'T'},draft=decisionFixture(()=>next,false,{data});await draft.decide('merge',{merged_after:'unsent draft'});assert.equal(draft.ui.draftText,'unsent draft');assert.equal(draft.ui.draftBasis.review_token,'owner-token');assert.equal(draft.removed.length,0);assert.equal(data.reviewable,false);assert.match(draft.events.at(-1)[1].text,/do not repeat/);
 const late=joinedDecisionFixture();Object.assign(late.acknowledged,next);late.setCurrent(false);await late.decide('E','merge');assert.equal(late.events.length,0);assert.equal(late.calls.filter(call=>typeof call==='string').length,0);
});

test('minimal post-effect comparison failure retains exact outcome without fabricating a comparison or replaying',async()=>{
 for(const recorded of [false,true]){
  const f=joinedDecisionFixture(),next={project:'P',turn_id:'T',proposal_version:'V',preview_unavailable:true,reviewable:false,warning:'Known source outcome retained; comparison unavailable. Inspect exact receipts; do not repeat the effect.',application:recorded?{id:'WA-recorded',complete:true,project:'P',turn_id:'T',candidate_version:'V',candidate_edit_ids:['E']}:{complete:false,source_applied:true,application_tracking:{status:'UNPROVED',attempted_id:'WA-unrecorded'}}};
  for(const key of Object.keys(f.acknowledged))delete f.acknowledged[key];Object.assign(f.acknowledged,next);
  const result=await f.decide('E','merge',{review_token:'original-owner-token',merged_after:'draft'});assert.equal(result,f.acknowledged);assert.deepEqual(f.calls.filter(call=>typeof call==='string'),['clear','document']);assert.equal(f.calls.filter(call=>typeof call==='object').length,1);assert.equal(result.edits,undefined);assert.match(f.events[0][0],/comparison unavailable/);
  const data={turn_id:'T'},draft=decisionFixture(()=>result,false,{data});await draft.decide('merge',{merged_after:'unsent draft'});assert.equal(draft.ui.draftText,'unsent draft');assert.equal(draft.removed.length,0);assert.equal(data.reviewable,false);assert.match(draft.events.at(-1)[1].text,/do not repeat/);
 }
});

test('actual partial-result callback returns known outcome when clear or render maintenance throws',async()=>{
 for(const step of ['clear','render']){
  const f=joinedDecisionFixture(step),next=f.acknowledged;next.application={complete:false,source_applied:true,application_tracking:{status:'UNPROVED',attempted_id:'WA-unrecorded'}};next.application_tracking=next.application.application_tracking;next.warning='Source changes applied; tracking unproved. Inspect exact feedback; do not repeat the effect.';next.reviewable=false;if(step==='clear'){next.preview_unavailable=true;delete next.edits;}
  const result=await f.decide('E','merge',{review_token:'original-owner-token',merged_after:'draft'});assert.equal(result,next);assert.equal(f.calls.filter(call=>typeof call==='object').length,1);assert.deepEqual(f.calls.filter(call=>typeof call==='string'),[step]);assert.match(f.events.at(-1)[0],/Source changes applied; tracking unproved/);assert.match(f.events.at(-1)[0],/View maintenance is unavailable/);assert.match(f.events.at(-1)[0],/do not repeat/i);
  const draft=decisionFixture(()=>result);await draft.decide('merge',{merged_after:'unsent draft'});assert.equal(draft.ui.draftText,'unsent draft');assert.equal(draft.ui.draftBasis.review_token,'owner-token');assert.equal(draft.removed.length,0);
 }
});

const settledWalkSource=walkSource();
const recordedCode=settledWalkSource.slice(settledWalkSource.indexOf('function showRecordedProposal('),settledWalkSource.indexOf('function manuscriptDraftRanges(',settledWalkSource.indexOf('function showRecordedProposal(')));
class RecordedNode{constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];this.dataset={};this.attrs={};this.isConnected=true;}append(...nodes){for(const node of nodes){if(node.parentElement)node.parentElement.children=node.parentElement.children.filter(n=>n!==node);node.parentElement=this;this.children.push(node);}}prepend(node){this.append(node);this.children.unshift(this.children.pop());}replaceChildren(){this.children=[];}setAttribute(key,value){this.attrs[key]=value;}remove(){this.parentElement.children=this.parentElement.children.filter(n=>n!==this);this.isConnected=false;}all(){return [this,...this.children.flatMap(n=>n.all?.()||[])];}querySelectorAll(){return this.all().filter(n=>n.dataset.retainedProposalDraft!=null);}}
test('actual terminal render followed by actual acknowledgement removes only settled local-draft DOM and retains newer text',async()=>{for(const newer of [false,true]){let renderError;const docEl=new RecordedNode('article'),key='laplace:proposal-draft:P:T:V:E',cache=new Map([[key,'unsent draft']]),storage={getItem:key=>cache.get(key)??null,removeItem:key=>cache.delete(key)};const base=decisionFixture(async ui=>{const f=joinedDecisionFixture();const {ui:state}=base;if(newer){state.draftText='newer retained typing';cache.set(key,state.draftText);}const render=new Function('bindings',`let attentionBlockId=null;const {el,asChrome,applicationSourceStateLabel,proposalModels,paintRevisionDifference,S,proposalUiStates,proposalDraftKey,localStorage,docEl,proposalView,syncRevisionHighlights,measure,emit,captureFocus,noteAttention}=bindings;${recordedCode};return showRecordedProposal;`)({noteAttention(){},el:(tag,cls,text)=>{const node=new RecordedNode(tag,text||'');node.className=cls;return node;},asChrome:node=>node,applicationSourceStateLabel:()=>'',proposalModels:()=>[],paintRevisionDifference(){},S:{corpus:'P',blocks:[]},proposalUiStates:new Map([[key,state]]),proposalDraftKey,localStorage:storage,docEl,proposalView:{},syncRevisionHighlights(){},measure(){},emit(){},captureFocus(){}});f.acknowledged.proposal_state='applied';f.acknowledged.edits[0]={...f.acknowledged.edits[0],file:'chapter.tex',before:'original',after:'unsent draft'};try{render(f.acknowledged,{focus:false});assert.equal(docEl.querySelectorAll().length,1);}catch(error){renderError=error;throw error;}return f.acknowledged;},false,{draftKey:key,localStorage:storage,docEl});await base.decide('merge',{merged_after:'unsent draft'});if(renderError)throw renderError;assert.equal(docEl.querySelectorAll().length,newer?1:0);if(newer){assert.equal(base.ui.draftText,'newer retained typing');const kept=docEl.querySelectorAll()[0].all().find(n=>n.tag==='textarea');assert.equal(kept.value,'newer retained typing');}}});


test('actual TeX parser literal escapes reach the same qualified Work/material DOM callback',async()=>{
 const target={owner:'repository',repository:'laplace',path:'src/atlas/store.py'};
 const urls=['/work/state?'+new URLSearchParams({project:'B',view:'detail',id:'WORK-source',limit:'1'}),'/projects/material-references?'+new URLSearchParams({project:'B',view:'preview',target:JSON.stringify(target),limit:'16000'})];
 const tex=urls.map(url=>'\\href{'+url.replaceAll('&','\\&').replaceAll('%','\\%')+'}{Read owner}');
 tex.push('\\href{/work/state?project=B\\unknownmacro&view=detail&id=W}{Unknown}');
 const pieces=JSON.parse(ownerPython(['-c','import json,sys;from laplace.manuscript.walk import tex_pieces;print(json.dumps([tex_pieces(text,{}) for text in json.loads(sys.argv[1])]))',JSON.stringify(tex)]));
 for(let i=0;i<2;i++){const part=pieces[i].find(row=>row.t==='href');assert.equal(part.url,urls[i]);const f=linkFixture(),link=f.render(part.url);await link.listeners.click({preventDefault(){},stopPropagation(){}});assert.equal(f.posted[0].message.url,urls[i]);assert.equal(f.reads.length,0);}
 const unknown=pieces[2].find(row=>row.t==='href');assert.equal(unknown.url,null);assert.ok(unknown.url_source);assert.equal(linkFixture().render(unknown.url).href,undefined);
});

const warningWorkspaceSource=await readFile(new URL('../src/laplace/web/static_shared/workspace-notices.mjs',import.meta.url),'utf8');   // the status line owner (M5 S2 F1)
const warningNoticeCode=warningWorkspaceSource.slice(warningWorkspaceSource.indexOf('  let noticeOwner=null;'),warningWorkspaceSource.indexOf('  const guard=fn',warningWorkspaceSource.indexOf('  let noticeOwner=null;')));
test('actual acknowledged callback clears only its settled refresh warning, unrelated notices and newer draft survive',async()=>{
 const {createManuscriptRefresh}=await import('../src/laplace/web/static_shared/manuscript-editing.mjs');
 for(const mode of ['settled','unrelated','newer']){
  const node={dataset:{},textContent:'',classList:{toggle(){}}},root={querySelector:()=>node};
  const notices=new Function('root',warningNoticeCode+';return {notice,clearRefreshWarning};')(root);
  let revision='one',dirty=true;const head={project:'P',current_revision:'two',source_observation:{schema_version:'laplace.manuscript-source-observation/1'}};
  const walk={ready:()=>true,documentVersion:()=>revision,sourceObservation:()=>({current_revision:revision}),editState:()=>({proposal_dirty:dirty}),refresh:async()=>{throw Error('No extra body refresh required');}};
  let bodies=0;const refresh=createManuscriptRefresh({project:'P',observe:async()=>head,read:async()=>{bodies++;throw Error('Dirty draft must not hydrate');},getWalk:()=>walk,visible:()=>true,status:notices.notice,clearStatus:notices.clearRefreshWarning});
  await refresh.check();assert.match(node.textContent,/local draft is preserved/);assert.equal(bodies,0);
  const f=decisionFixture(ui=>{revision='two';dirty=mode==='newer';if(mode==='unrelated')notices.notice('Unrelated engine warning',true);if(mode==='newer')ui.draftText='newer unsent draft';return ack();},false,{emit:(kind)=>{if(kind==='edit-settled')refresh.settled();}});
  await f.decide('merge',{merged_after:'unsent draft'});
  if(mode==='settled')assert.equal(node.textContent,'');
  if(mode==='unrelated')assert.equal(node.textContent,'Unrelated engine warning');
  if(mode==='newer'){await refresh.check();assert.match(node.textContent,/local draft is preserved/);assert.equal(f.ui.draftText,'newer unsent draft');}
  assert.equal(bodies,0);refresh.destroy();
 }
});

const hostWalkSource=walkSource();
function hostSection(start,end){const at=hostWalkSource.indexOf(start);return hostWalkSource.slice(at,hostWalkSource.indexOf(end,at));}
const hostSnapshotCode=walkDeclarations('snapshotEdit');
const hostParkCode=walkDeclarations('parkEdit');
const hostEditingCode=hostSection('function eventEditingHost(', 'function onBeforeInput(');
const hostInputCode=hostSection('function onEditInput(', 'function wireEditor(');
const hostCommitCode=walkDeclarations('commitAll');
function hostListener(name){const at=hostWalkSource.indexOf('  docEl.addEventListener("'+name+'",');return hostWalkSource.slice(at,hostWalkSource.indexOf('\n  });',at)+6);}
test('actual editing focus establishes pristine before paste, input parks and Save follows existing guarded batch',async()=>{
 for(const targetRoot of [false,true]){
  const E={blockId:'',pristine:'',dirty:false,scope:'',timer:0},P=new Map(),listeners={},calls=[];
  const docEl={matches:()=>false,closest:()=>null,addEventListener:(kind,callback)=>listeners[kind]=callback};
  const block=(id,text)=>{const body={text,matches:()=>false,closest:selector=>selector.startsWith('.blk-body')?body:null,contains:node=>node===body||node?.parentElement===body};const value={id,tex:text,el:{dataset:{block:id}},bodyEl:body};body.block=value;return value;};
  const a=block('A','Original guarded text'),b=block('B','Another paragraph'),map=new Map([['A',a],['B',b]]);let range={startContainer:{nodeType:3,parentElement:a.bodyEl},endContainer:{nodeType:3,parentElement:a.bodyEl}};
  const bindings={INFLIGHT:new Set(),QUEUE:{why:''},NOT_SAVED:{why:''},D:{sourceObservation:{source_observation:{selection_identity:"inspected-selection"}}},E,P,docEl,expectedOf:()=>[],assignBasis:(t,b)=>Object.assign(t,{tex:b.tex,src:b.src,expectedSelection:b.expectedSelection,expected:b.expected}),captureBasis:b=>({tex:b.tex||'',src:{file:'chapter.tex',lineStart:2,lineEnd:2},expectedSelection:'inspected-selection',expected:[]}),draftAuthority:basis=>basis.review?null:(Array.isArray(basis.expected)?basis.expected:null),holdForReview(){},REVIEW_WORDS:{},blockById:map,C:{},RL:false,CARD:null,cardNote:null,document:{getSelection:()=>({rangeCount:1,getRangeAt:()=>range}),getElementById:()=>null},hostText:host=>host.text,closestBlock:host=>{const value=host?.block||host?.parentElement?.block;return value?.el||null;},srcOf:value=>({file:'chapter.tex',lineStart:value.id==='A'?1:2,lineEnd:value.id==='A'?1:2}),setEditScope(){},clearEdit(){E.blockId='';E.dirty=false;},autosize(){},paintParked(){},paintDeposits(){},renderBand(){},yieldComposer(){},showCard(){},paintCardState(){},positionCard(){},parkDiff:()=>({}),clearTimeout(){},emit(){},commitEdit:async()=>{const value=map.get(E.blockId);calls.push({block:value.id,before:E.pristine,after:value.bodyEl.text});P.delete(value.id);E.dirty=false;return {applied:true,id:'actual-owner-fixture-receipt'};}};
  const declarations=Object.keys(bindings).join(',');const state=new Function('bindings',`const {${declarations}}=bindings;${hostSection('function parkEntry(', '/** The changed span')}${hostParkCode}${hostSnapshotCode}${hostEditingCode}${walkDeclarations('onBeforeInput')}${hostInputCode}${hostCommitCode}${hostListener('focusin')}${hostListener('focusout')};return {onBeforeInput,onEditInput,commitAll};`)(bindings);
  bindings.document.execCommand=(command,_,text)=>{assert.equal(command,'insertText');assert.equal(E.pristine,'Original guarded text');a.bodyEl.text=text;state.onEditInput({target:targetRoot?docEl:a.bodyEl});};
  listeners.focusin({target:targetRoot?docEl:a.bodyEl});assert.equal(E.blockId,'A');assert.equal(E.pristine,'Original guarded text');
  state.onBeforeInput({target:targetRoot?docEl:a.bodyEl,inputType:'insertFromPaste',dataTransfer:{getData:()=> 'Pasted replacement'},preventDefault(){}});assert.equal(E.dirty,true);assert.equal(P.get('A').pristine,'Original guarded text');assert.equal(P.get('A').text,'Pasted replacement');
  range={startContainer:{nodeType:3,parentElement:b.bodyEl}};listeners.focusout({target:targetRoot?docEl:a.bodyEl,relatedTarget:{}});assert.equal(E.blockId,'');assert.equal(P.get('A').text,'Pasted replacement');assert.equal(P.has('B'),false);
  const batch=await state.commitAll();assert.equal(batch.applied.length,1);assert.deepEqual(calls,[{block:'A',before:'Original guarded text',after:'Pasted replacement'}]);assert.ok(!batch.message.includes('No unsaved edits'));
 }
});
test('embedding wrapper cannot overrule walk source-qualified editing host authority',async()=>{const panel=await readFile(new URL('../src/laplace/web/static_shared/writing-panel.mjs',import.meta.url),'utf8'),start=panel.indexOf("  root.classList.add('writing-enabled','writing-embedded')"),end=panel.indexOf('  const contents=',start);const snippet=panel.slice(start,end),doc={setAttribute(){}};new Function('root','$',snippet)({classList:{add(){}},dataset:{}},()=>doc);assert.equal(doc.contentEditable,'false');});


test('selected body preserves explicit owner parent count and never promotes child readiness',async()=>{
 const data=JSON.parse(await readFile(new URL('./fixtures/proposal-navigation-owner-81a740812.json',import.meta.url),'utf8')),id=data.edit.edits[0].edit_id;
 const parent={...data.summary,remaining:2,read_scope:{kind:'candidate'}},child={...data.edit,remaining:1,read_scope:{kind:'selected-edit'}};
 const joined=selectedProposalBody(parent,child,id);assert.equal(joined.remaining,1);assert.equal(joined.candidate_summary.remaining,2);assert.match(proposalReviewStatus(joined).text,/2 changes.*candidate summary/);
 const stale=selectedProposalBody(parent,{...child,edits:[{...child.edits[0],basis_currentness:'STALE',allowed_actions:[]}]},id);assert.equal(stale.candidate_summary.remaining,2);assert.deepEqual(stale.edits[0].allowed_actions,[]);
 for(const remaining of [1,0])assert.equal(proposalReviewStatus(selectedProposalBody({...parent,remaining},child,id)).remaining,remaining);
 assert.match(proposalReviewStatus(child).text,/whole candidate count is not inspected/);assert.equal(proposalReviewStatus({edits:[{},{}]}).remaining,null);
});
test('actual walk banner reports named owner scope rather than number of hydrated bodies',()=>{
 const code=settledWalkSource.match(/const reviewStatus=proposalReviewStatus\(data\);emit\('editor-status',\{text:reviewStatus.text\}\);return pending.length;/)[0],events=[];
 const report=new Function('data','pending','emit','proposalReviewStatus',code);const returned=report({candidate_summary:{remaining:2}},[{}],(...args)=>events.push(args),proposalReviewStatus);
 assert.equal(returned,1);assert.match(events[0][1].text,/2 changes.*candidate summary/);
});


test('blank deletion Undo expands only into recorded nonempty neighbouring hunk, with exact reversible byte guard',()=>{
 const door=(text,span)=>[...text.split('\n').slice(0,span.line_start-1),...span.after.split('\n'),...text.split('\n').slice(span.line_end)].join('\n');
 for(const [source,line,before] of [['Heading\n\nTail',2,'Deleted paragraph.'],['\nTail',1,'Opening paragraph.'],['Heading\n',2,'Final paragraph.'],['Heading\n \t\nTail',2,'Deleted paragraph.']]){
  const after=source.split('\n')[line-1],change=captureSourceChange(source,{file:'chapter.tex',line_start:line,before,after}),span=historySpan(source,change);
  assert.ok(span.before.trim());assert.equal(source.split('\n').slice(span.line_start-1,span.line_end).join('\n'),span.before);const restored=door(source,span);assert.equal(restored,historyReplacement(source,change));assert.equal(historyReplacement(restored,change,false),source);assert.ok(span.before.length<40);
 }
});
test('blank deletion inverse refuses missing, ambiguous or altered recorded location',()=>{
 const change=captureSourceChange('Heading\n\nTail',{file:'chapter.tex',line_start:2,before:'Deleted.',after:''});
 assert.throws(()=>historySpan('Changed\n\nTail',change),/safely locate/);assert.throws(()=>historySpan('Heading\n\nTail\nHeading\n\nTail',change),/safely locate/);
 assert.throws(()=>historySpan('',{before:'Gone',after:''}),/safely locate/);assert.throws(()=>historySpan(' \n\n ',{before:'Gone',after:'',prefix:' \n',suffix:'\n '}),/nonempty/);
 const long='L'.repeat(600)+'\n\n'+'R'.repeat(600),partial=captureSourceChange(long,{before:'Gone',after:'',line_start:2}),edited='Unrelated changed start '+long;const wide=historySpan(edited,partial);assert.ok(wide.before.trim());assert.ok(wide.before.length>500);assert.equal(historyReplacement(edited,partial),'Unrelated changed start '+'L'.repeat(600)+'\nGone\n'+'R'.repeat(600));
 const current='Unrelated new introduction\nHeading\n\nTail';assert.equal(historyReplacement(current,change),'Unrelated new introduction\nHeading\nDeleted.\nTail');
});
test('actual whole-paragraph Backspace snapshots before native input and parks empty draft with Autosave off',()=>{
 const E={blockId:'',pristine:'',dirty:false,scope:'',timer:0},P=new Map(),events=[],listeners={};const text='Prose with first reference and second reference';
 const host={nodeType:1,text,matches:()=>false,closest:selector=>selector.startsWith('.blk-body')?host:null,contains:node=>node===host||node?.parentElement===host},b={id:'A',kind:'para',tex:'Prose \\ref{one} and \\ref{two}.',el:{dataset:{block:'A'}},bodyEl:host};host.block=b;
 const range={startContainer:host,endContainer:host,startOffset:0,endOffset:text.length,collapsed:false},docEl={matches:()=>false,closest:()=>null,addEventListener:(kind,callback)=>listeners[kind]=callback};
 const bindings={D:{sourceObservation:{source_observation:{selection_identity:"inspected-selection"}}},E,P,docEl,expectedOf:()=>[],assignBasis:(t,b)=>Object.assign(t,{tex:b.tex,src:b.src,expectedSelection:b.expectedSelection,expected:b.expected}),captureBasis:b=>({tex:b.tex||'',src:{file:'chapter.tex',lineStart:2,lineEnd:2},expectedSelection:'inspected-selection',expected:[]}),draftAuthority:basis=>basis.review?null:(Array.isArray(basis.expected)?basis.expected:null),holdForReview(){},REVIEW_WORDS:{},blockById:new Map([['A',b]]),C:{actor:'author'},RL:false,CARD:null,cardNote:null,document:{getSelection:()=>({rangeCount:1,getRangeAt:()=>range}),getElementById:()=>({classList:{contains:()=>true}})},localStorage:{getItem:()=> 'off'},setTimeout:()=>{throw Error('Autosave off must schedule no source effect');},hostText:node=>node.text,closestBlock:node=>node?.block?.el||node?.parentElement?.block?.el,srcOf:()=>({file:'chapter.tex',lineStart:2,lineEnd:2}),offsetIn:(node,container,offset)=>offset,setEditScope(){},paintParked(){},paintDeposits(){},renderBand(){},yieldComposer(){},showCard(){},paintCardState(){},positionCard(){},parkDiff:()=>({}),clearTimeout(){},autosize(){},emit:(...args)=>events.push(args),deleteBlock:()=>{throw Error('Keyboard deletion must not call immediate structural write');}};
 const declarations=Object.keys(bindings).join(','),state=new Function('bindings',`const {${declarations}}=bindings;${hostSection('function parkEntry(', '/** The changed span')}${hostParkCode}${hostSnapshotCode}${hostEditingCode}${walkDeclarations('onBeforeInput')}${hostInputCode};return {onBeforeInput,onEditInput};`)(bindings);
 const event={target:host,inputType:'deleteContentBackward',preventDefault(){throw Error('Native deletion/undo stack should remain available');}};state.onBeforeInput(event);assert.equal(E.pristine,text);assert.equal(E.dirty,false);host.text='';state.onEditInput({target:host});assert.equal(E.dirty,true);assert.equal(P.get('A').text,'');assert.equal(P.get('A').pristine,text);assert.equal(E.timer,0);
 const at=hostWalkSource.indexOf('async function commitEdit('),until=hostWalkSource.indexOf('  setPayload(payload,',at),code=hostWalkSource.slice(at,until)+'return payload;}';
 const taggedParagraph=new Function(hostSection('function taggedParagraph(','function presentationOwner(')+'return taggedParagraph;')();
 const more={...bindings,INFLIGHT:new Set(),QUEUE:{why:''},NOT_SAVED:{why:''},taggedParagraph,pendingPresentationSplits:new Map(),setPayload:(body,key,value)=>{body[key]=value;return body;},RELOAD_INFLIGHT:null,sourceForRenderedRange:()=>'',pieceTypeAt:()=> 'text',anchorFromPristine:()=>({file:'chapter.tex',lineStart:2,lineEnd:2}),sourceRequest:value=>value,emptyParagraphSource,toSourceRegister:value=>value,expectedOf:()=>[]};
 const commit=new Function('bindings',`const {${Object.keys(more).join(',')}}=bindings;${code};return commitEdit;`)(more);return commit('explicit-save').then(payload=>{assert.equal(payload.before,b.tex);assert.equal(payload.after,'\\par');assert.deepEqual(payload.expected,[]);});
});


const deleteCode=hostWalkSource.slice(hostWalkSource.indexOf('async function deleteBlock(id)'),hostWalkSource.indexOf('  const result = await saveSourceChange(payload);',hostWalkSource.indexOf('async function deleteBlock(id)')))+'return payload;}';
function structuralDeleteFixture(source,{dirty=false,tex='Sole paragraph.'}={}){
 const E={blockId:'B',dirty},block={id:'B',kind:'para',tex,bodyEl:{},el:{}},events=[],calls=[];
 const bindings={E,P:new Map(),REVIEW_WORDS:{},blockById:new Map([['B',block]]),srcOf:()=>({file:'chapter.tex',lineStart:source.includes('\n')?2:1,lineEnd:source.includes('\n')?2:1}),RELOAD_INFLIGHT:null,C:{actor:'author'},readEditorSource:async()=>{calls.push('read');return source;},captureSourceChange,historySpan,commitEdit:async()=>{calls.push('effect');E.dirty=false;},emit:(...args)=>events.push(args),S:{blocks:[block]},hostText:()=>tex,sourceRequest:parts=>parts,expectedOf:()=>[],blockAtSpan:()=>null};
 const run=new Function('bindings',`const {${Object.keys(bindings).join(',')}}=bindings;${deleteCode};return deleteBlock;`)(bindings);return {run,calls,events};
}
test('explicit sole paragraph Delete refuses before all effects, offers ordinary empty draft path',async()=>{
 for(const dirty of [false,true]){const f=structuralDeleteFixture('Sole paragraph.',{dirty});assert.equal(await f.run('B'),false);assert.deepEqual(f.calls,['read']);assert.match(f.events.at(-1)[1].text,/not deleted.*Clear its text and Save/);}
});
test('explicit structural Delete reuses inverse hunk to guard both paragraph and current recoverability context',async()=>{
 const source='Long previous '+('words '.repeat(100))+'\nSole paragraph.\nLong next '+('words '.repeat(100)),f=structuralDeleteFixture(source),payload=await f.run('B');
 assert.ok(payload.before.includes('Sole paragraph.'));assert.ok(payload.after.trim());const lines=source.split('\n');assert.equal(lines.slice(payload.lineStart-1,payload.lineEnd).join('\n'),payload.before);const post=[...lines.slice(0,payload.lineStart-1),...payload.after.split('\n'),...lines.slice(payload.lineEnd)].join('\n');assert.equal(post,source.replace('Sole paragraph.',''));assert.deepEqual(f.calls,['read']);
});
test('paper input status consumes shared editState so native Undo clean state is not an independent unsaved flag',async()=>{
 const panel=await readFile(new URL('../src/laplace/web/static_shared/writing-panel.mjs',import.meta.url),'utf8'),code=panel.split('\n').find(line=>line.includes("$('#paper').addEventListener('input'"));let input,held={dirty:true,parked:1,save:{word:'Unsaved changes',text:'Unsaved changes',full:'Unsaved changes'}};const status={classList:{remove(){}}};new Function('send','$','window','localStorage','editorStatus',code)(()=>{},()=>({addEventListener:(kind,callback)=>input=callback}),{walk:{editState:()=>held}},{getItem:()=> 'off'},status);
 const event={target:{closest:()=>null,matches:()=>false}};input(event);assert.match(status.textContent,/Unsaved/);held={dirty:false,parked:0,save:null};input(event);assert.equal(status.textContent,'No unsaved manuscript edits');held={dirty:false,parked:0,committing:true,save:{word:'Saving',text:'Saving',full:'Saving'}};input(event);assert.equal(status.textContent,'Saving');
 input({target:{closest:selector=>selector==='.proposal-merge'?{}:null,matches:()=>false}});assert.equal(status.textContent,'Proposed draft saved locally');
});

test('the idle poll accepts an unchanged identity answer and reads no document body',async()=>{
 const {createManuscriptRefresh}=await import('../src/laplace/web/static_shared/manuscript-editing.mjs');
 let observed=0,bodies=0;const walk={ready:()=>true,documentVersion:()=>'v1',sourceObservation:()=>({current_revision:'rev-1'}),editState:()=>({}),refresh:async()=>{throw Error('no refresh expected');}};
 const refresh=createManuscriptRefresh({project:'P',observe:async()=>{observed++;return {project:'P',unchanged:true,summary_revision:'sha256:'+'a'.repeat(64),document_status:'READY'};},read:async()=>{bodies++;throw Error('an unchanged answer must not hydrate');},getWalk:()=>walk,visible:()=>true});
 const result=await refresh.check();assert.deepEqual([result.checked,result.changed],[true,false]);assert.equal(observed,1);assert.equal(bodies,0);
 const stale=createManuscriptRefresh({project:'P',observe:async()=>({project:'P',unchanged:true}),read:async()=>{bodies++;},getWalk:()=>walk,visible:()=>true,status:()=>{}});
 const refused=await stale.check();assert.equal(refused.checked,false);assert.match(refused.error,/incompatible source observation/);assert.equal(bodies,0);
 refresh.destroy();stale.destroy();
});

test('a scoped reload plan reconciles every held section whose source moved and never calls undelivered sections current',async()=>{
 const {planScopedReload,createManuscriptRefresh}=await import('../src/laplace/web/static_shared/manuscript-editing.mjs');
 const held=[{id:'alpha',file:'body.tex',blocks:2,file_revision:'b1'},{id:'bravo',file:'body.tex',blocks:3,file_revision:'b1'},{id:'three',file:'extra.tex',blocks:1,file_revision:'e1'}];
 const witness=Object.fromEntries(held.map(row=>[row.id,row.file_revision]));
 // Reproduction: Alpha and Bravo changed externally; only Alpha was requested.
 const delivered={section_index:[{id:'alpha',file:'body.tex',blocks:2,file_revision:'b2'},{id:'bravo',file:'body.tex',blocks:3,file_revision:'b2'},{id:'three',file:'extra.tex',blocks:1,file_revision:'e1'}],selected_sections:['alpha']};
 const plan=planScopedReload({heldIndex:held,heldWitness:witness,delivered});
 assert.deepEqual(plan,{structureChanged:false,staleSections:['bravo'],witness:{alpha:'b2',bravo:'b2',three:'e1'}});
 // A change in another file leaves this file's sections current.
 const elsewhere={section_index:held.map(row=>row.id==='three'?{...row,file_revision:'e2'}:row),selected_sections:['alpha']};
 assert.deepEqual(planScopedReload({heldIndex:held,heldWitness:witness,delivered:elsewhere}).staleSections,['three']);
 assert.deepEqual(planScopedReload({heldIndex:held,heldWitness:witness,delivered:{section_index:held,selected_sections:['alpha']}}).staleSections,[]);
 // A changed section list is a structure change: whole read.
 assert.equal(planScopedReload({heldIndex:held,heldWitness:witness,delivered:{section_index:[held[0],held[2]],selected_sections:['alpha']}}).structureChanged,true);
 assert.equal(planScopedReload({heldIndex:held,heldWitness:witness,delivered:{section_index:[...held,{id:'four',file:'extra.tex',blocks:1,file_revision:'e1'}],selected_sections:['alpha']}}).structureChanged,true);
 // While a held section is stale the walk withholds its currentness claim: the poll reads the body.
 let bodies=0,applied=0;const walk={ready:()=>true,documentVersion:()=>'held',sourceObservation:()=>({current_revision:null,stale_sections:['bravo']}),editState:()=>({}),refresh:async()=>{applied++;return true;}};
 const refresh=createManuscriptRefresh({project:'P',observe:async()=>({project:'P',current_revision:'rev-2',summary_revision:'s2',source_observation:{schema_version:'laplace.manuscript-source-observation/1'}}),read:async()=>{bodies++;return {ok:true,project:'P',current_revision:'rev-2',source_observation:{schema_version:'laplace.manuscript-source-observation/1'},root:'main.tex',sections:[{id:'alpha',blocks:[]}]};},getWalk:()=>walk,visible:()=>true});
 const result=await refresh.check();assert.equal(bodies,1);assert.equal(applied,1);assert.equal(result.refreshed,true);refresh.destroy();
});
