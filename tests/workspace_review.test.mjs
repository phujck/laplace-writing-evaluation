import {test} from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
const source=(await readFile(new URL('../src/laplace/web/static_shared/workspace-review.mjs',import.meta.url),'utf8')).replace("'/shared/concept-reader.mjs'",JSON.stringify(new URL('../src/laplace/web/static_shared/concept-reader.mjs',import.meta.url).href)).replace("'./manuscript-editing.mjs'",JSON.stringify(new URL('../src/laplace/web/static_shared/manuscript-editing.mjs',import.meta.url).href)).replace("'./workspace-history.mjs'",JSON.stringify(new URL('../src/laplace/web/static_shared/workspace-history.mjs',import.meta.url).href)).replace("'./workspace-presentation.mjs'",JSON.stringify(new URL('../src/laplace/web/static_shared/workspace-presentation.mjs',import.meta.url).href));
const {mountReview,createProjectReview,proposalStandingLabel}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
class Node{constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this._text='';this.className='';this.classList={add(){}};}set textContent(text){this._text=String(text||'');this.children=[];}get textContent(){return this._text+this.children.map(node=>node.textContent).join('');}append(...nodes){for(const node of nodes){node.parentElement=this;this.children.push(node);}}replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}setAttribute(key,value){this.attrs[key]=String(value);}all(){return [this,...this.children.flatMap(node=>node.all())];}querySelectorAll(selector){return this.all().slice(1).filter(node=>selector==='[data-correction-id]'?'correctionId' in node.dataset:selector.startsWith('.')?node.className===selector.slice(1):node.tag===selector);}querySelector(selector){return this.querySelectorAll(selector)[0]||null;}remove(){this.parentElement.children=this.parentElement.children.filter(node=>node!==this);}focus(){document.activeElement=this;}scrollIntoView(){this.scrolled=true;}contains(node){return this.all().includes(node);}setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;}}
function dom(){globalThis.document={createElement:tag=>new Node(tag),createTextNode:text=>{const node=new Node('#text');node.textContent=text;return node;},querySelector:()=>({})};return new Node('main');}
const find=(host,label)=>host.all().find(node=>node.tag==='button'&&node.textContent===label);
async function fixture({closed=false,replySupport=true,extra=0,correctionId=null,gate=null,noteAnchor=null}={}){const host=dom(),original={id:'original-review',scope:'project',kind:'note',by:'author',status:closed?'superseded':'open',text:'The original six-point scientific review must remain active.',anchor:noteAnchor||{}},state={revision:41,corrections:[original,...Array.from({length:extra},(_,i)=>({id:'older-note-'+i,scope:'project',kind:'note',by:'author',status:'open',text:'Paged note '+i,reply_to:i===extra-1?original.id:null}))]},calls=[],statuses=[];const reads=[];const request=async(path,payload)=>{if(path.startsWith('/authoring/history?'))reads.push(path);if(gate?.wait)await gate.wait(path);if(path.startsWith('/authoring/history?')){const q=new URL(path,'http://fixture').searchParams,category=row=>row.correction_category||({project:'project-notes',passage:'passage-comments',global:'global-notes'}[row.scope]||'other'),counts=Object.fromEntries(['project-notes','passage-comments','global-notes','applied-edits','other'].map(key=>[key,{open:0,resolved:0,dismissed:0,superseded:0,unknown:0}]));for(const row of state.corrections)counts[category(row)][row.status||'open']++;if(q.get('id')){const row=state.corrections.find(row=>row.id===q.get('id'));if(!row)throw Error('author history item is unavailable');return {revision:state.revision,as_of:'cut:'+state.revision,item:{...row,correction_category:category(row)},counts};}if(q.get('as_of')&&q.get('as_of')!=='cut:'+state.revision)throw Error('CHANGED_INPUT: refresh');const rows=[...state.corrections].reverse().filter(row=>(!q.get('correction_category')||(q.get('correction_category')==='notes'?category(row)!=='applied-edits':category(row)===q.get('correction_category')))&&(!q.get('status')||(q.get('status')==='closed'?(row.status||'open')!=='open':(row.status||'open')===q.get('status'))));const offset=Number(q.get('offset')||0),limit=Number(q.get('limit')||20);return {revision:state.revision,as_of:'cut:'+state.revision,items:rows.slice(offset,offset+limit).map(row=>({...row,anchor:Object.fromEntries(Object.entries(row.anchor||{}).filter(([key])=>['file','section','section_id','lines','line_start','line_end'].includes(key))),correction_category:category(row)})),counts,total:rows.length,offset,next_offset:offset+limit<rows.length?offset+limit:null};}if(path.startsWith('/authoring/proposals?'))return {project:'book',view:'queue',as_of:'proposal-cut',count:0,proposals:[]};calls.push({path,payload});if(path==='/authoring/correction-status'){original.status=payload.status;original.status_history=[{status:payload.status,note:payload.note,by:'author'}];state.revision++;return {correction:original,status:original.status};}if(path==='/authoring/correction'){if(payload.base_revision!==state.revision)throw Error('CHANGED_INPUT: stale authoring revision');const correction={...payload,id:'reply',status:'open'};if(!replySupport)delete correction.reply_to;state.corrections.push(correction);state.revision++;return {correction};}throw Error(path);};const opened=[],discussed=[];await mountReview(host,{project:'book',initialFilter:'open',request,correctionId,onOpenPassage:value=>{opened.push(value);},onDiscuss:(text,value)=>{discussed.push({text,anchor:value});},status:(...args)=>statuses.push(args)});return {host,original,state,calls,statuses,request,reads,opened,discussed};}

test('Reply appends a threaded note without sending supersedes or retiring the original',async()=>{
 const {host,original,calls,state}=await fixture();await find(host,'Notes · 1').onclick();await find(host,'Reply').onclick();const form=host.querySelector('form');form.querySelector('textarea').value='Completed report and accessible source URL.';await form.onsubmit({preventDefault(){}});const saved=calls.find(call=>call.path==='/authoring/correction').payload;assert.equal(saved.reply_to,original.id);assert.equal(Object.hasOwn(saved,'supersedes'),false);assert.equal(original.status,'open');assert.equal(state.corrections.length,2);const parent=host.all().find(node=>node.tag==='button'&&node.textContent.startsWith('Reply to note '));assert.ok(parent);await parent.onclick();assert.equal(document.activeElement.dataset.correctionId,original.id);
});
test('superseded notes expose guarded Reopen and retain their status history',async()=>{
 const {host,original,calls}=await fixture({closed:true});await find(host,'Closed · 1').onclick();await find(host,'Reopen superseded note').onclick();assert.equal(calls[0].path,'/authoring/correction-status');assert.equal(calls[0].payload.id,original.id);assert.equal(calls[0].payload.base_revision,41);assert.equal(calls[0].payload.status,'open');assert.match(calls[0].payload.note,/replacement and prior history remain/);await find(host,'Notes · 1').onclick();await find(host,'Inspect full record').onclick();assert.ok(host.textContent.includes('Status history'));assert.ok(host.textContent.includes('original six-point scientific review'));assert.equal(original.status,'open');
});
test('an older engine cannot silently claim a reply link it did not save',async()=>{
 const {host,original,statuses,calls}=await fixture({replySupport:false});await find(host,'Notes · 1').onclick();await find(host,'Reply').onclick();const form=host.querySelector('form');form.querySelector('textarea').value='A follow-up.';await form.onsubmit({preventDefault(){}});assert.equal(original.status,'open');assert.equal(calls.length,1);assert.match(statuses.at(-1)[0],/did not retain the reply link/);assert.equal(statuses.at(-1)[1],true);
});


test('Review filters retain separate note and reply drafts; cancelling one preserves the other',async()=>{
 const {host,calls}=await fixture();await find(host,'New project note').onclick();
 const note=host.querySelector('textarea');note.value='Unsaved note across filters';note.oninput();
 await find(host,'Closed · 0').onclick();assert.equal(host.querySelector('textarea'),note);
 assert.equal(note.value,'Unsaved note across filters');
 await find(host,'Notes · 1').onclick();await find(host,'Reply').onclick();
 const reply=host.querySelectorAll('textarea').find(input=>input!==note);reply.value='Unsaved reply';reply.oninput();
 await find(host,'Comments · 0').onclick();assert.equal(host.querySelectorAll('textarea').length,2);
 const noteForm=note.parentElement;await noteForm.all().find(node=>node.tag==='button'&&node.textContent==='Cancel').onclick();
 assert.equal(host.querySelector('textarea'),reply);assert.equal(reply.value,'Unsaved reply');
 await reply.parentElement.onsubmit({preventDefault(){}});
 assert.equal(calls.at(-1).payload.reply_to,'original-review');assert.equal(calls.at(-1).payload.text,'Unsaved reply');
 assert.equal(host.querySelectorAll('textarea').length,0);
});


test('exact off-page reply focus preserves the page and all records remain reachable',async()=>{
 const {host,state}=await fixture({extra:42});await find(host,'Notes · 43').onclick();
 assert.match(host.textContent,/43 records · showing 1–20/);assert.ok(!host.querySelectorAll('[data-correction-id]').some(row=>row.dataset.correctionId==='original-review'));
 await find(host,'Reply to note original-review').onclick();assert.equal(document.activeElement.dataset.correctionId,'original-review');
 await find(host,'Back to review page').onclick();assert.match(host.textContent,/43 records · showing 1–20/);
 const ids=new Set(host.querySelectorAll('[data-correction-id]').map(row=>row.dataset.correctionId));
 while(find(host,'More records')){await find(host,'More records').onclick();for(const row of host.querySelectorAll('[data-correction-id]'))ids.add(row.dataset.correctionId);}
 assert.equal(ids.size,state.corrections.length);assert.equal(ids.has('original-review'),true);
});

test('focused correction works outside the initial category and retains its exact saved status',async()=>{
 const {host}=await fixture({extra:42,closed:true,correctionId:'original-review'});assert.equal(document.activeElement.dataset.correctionId,'original-review');assert.match(host.textContent,/superseded/);
});

test('a changed read cut is an error, refresh retains drafts without adopting their save guard',async()=>{
 const {host,state,calls,statuses}=await fixture({extra:42});await find(host,'Notes · 43').onclick();await find(host,'New project note').onclick();const note=host.querySelector('textarea');note.value='Retained exact draft';note.oninput();state.revision++;
 await find(host,'More records').onclick();assert.match(host.textContent,/CHANGED_INPUT/);assert.equal(host.querySelector('textarea'),note);
 await find(host,'Refresh review').onclick();assert.equal(note.value,'Retained exact draft');await note.parentElement.onsubmit({preventDefault(){}});assert.equal(calls.at(-1).payload.base_revision,41);assert.equal(host.querySelector('textarea'),note);assert.equal(statuses.at(-1)[1],true);
 await find(host,'Review current save revision').onclick();await find(host,'Use reviewed revision for this draft').onclick();await note.parentElement.onsubmit({preventDefault(){}});assert.equal(calls.at(-1).payload.base_revision,42);assert.equal(host.querySelector('textarea'),null);
});

test('late page reads cannot revive an older category; repaint retains active draft caret',async()=>{
 const gate={wait:null},{host}=await fixture({extra:42,gate});await find(host,'Notes · 43').onclick();await find(host,'New project note').onclick();const note=host.querySelector('textarea');note.value='Retained caret draft';note.oninput();note.focus();note.setSelectionRange(5,7);
 let release;gate.wait=path=>path.includes('offset=20')?new Promise(resolve=>{release=resolve;}):Promise.resolve();const earlier=find(host,'More records').onclick();await new Promise(resolve=>setImmediate(resolve));await find(host,'Comments · 0').onclick();release();await earlier;
 assert.ok(host.textContent.includes('No records in this review category.'));assert.ok(!host.querySelectorAll('[data-correction-id]').length);assert.equal(document.activeElement,note);assert.equal(note.selectionStart,5);assert.equal(note.selectionEnd,7);assert.equal(note.value,'Retained caret draft');
});

test('short-note context actions lazily retain exact quote and passage basis omitted from the page',async()=>{
 const basis={file:'chapter.tex',line_start:3,line_end:3,quote:'Exact original passage now moved.',passage_before:'Original bounded source basis.'};
 const {host,reads,opened,discussed,calls}=await fixture({noteAnchor:basis});await find(host,'Notes · 1').onclick();assert.ok(!host.textContent.includes(basis.quote));
 await find(host,'Open passage').onclick();assert.deepEqual(opened.at(-1),basis);
 await find(host,'Address with Eigen').onclick();assert.deepEqual(discussed.at(-1).anchor,basis);
 await find(host,'Reply').onclick();assert.ok(host.textContent.includes(basis.quote));const note=host.querySelector('textarea');note.value='Anchored follow-up';await note.parentElement.onsubmit({preventDefault(){}});assert.deepEqual(calls.at(-1).payload.anchor,basis);assert.equal(calls.at(-1).payload.base_revision,41);
 assert.ok(reads.filter(path=>path.includes('id=original-review')).length>=3);
});

const pin=(project,id,version)=>({http:{method:'GET',url:'/authoring/proposal-preview?'+new URLSearchParams({project,id,proposal_version:version,record_id:'record-'+version,view:'summary'})},native_request:{verb:'read',target:project+'::'+id,payload:{id,proposal_version:version,record_id:'record-'+version,view:'summary'}}});
const proposal=(id='T',version='V',project='book')=>({id,project,proposal_version:version,read_handle:pin(project,id,version),edit_count:2,files:['chapter.tex']});
const queuePage=(rows,cut='cut',extra={})=>({project:'book',view:'queue',as_of:cut,proposals:rows,count:rows.length,count_basis:'current rows on this inspected page; total unknown until complete traversal',pagination:{next_read:null,remaining_candidates:0},coverage:{unavailable_candidate_records:[]},...extra});
function queueFixture(request){const calls=[],opened=[],statuses=[];const controller=createProjectReview({project:'book',events:null,document:null,request:async path=>{calls.push(path);return request(path,calls.length);},onReviewProposal:(...args)=>opened.push(args),status:(...args)=>statuses.push(args)});return {controller,calls,opened,statuses};}

test('project Review without a selected session reads one queue and opens only the selected owner handle',async()=>{
 const host=dom(),f=queueFixture(()=>queuePage([proposal()]));await mountReview(host,{project:'book',request:()=>{throw Error('No history/body requested');},proposalController:f.controller});
 assert.equal(f.calls.length,1);assert.match(f.calls[0],/view=queue/);assert.equal(f.opened.length,0);await find(host,'Review in manuscript').onclick();assert.deepEqual(f.opened,[['T',{proposalVersion:'V',readHandle:pin('book','T','V'),readOnly:false}]]);
});
test('queue has one in-flight owner read; repeated view mounts reuse it without selected body reads',async()=>{
 let release;const f=queueFixture(()=>new Promise(resolve=>release=resolve));const one=f.controller.read(),two=f.controller.read();await new Promise(resolve=>setImmediate(resolve));assert.equal(f.calls.length,1);release(queuePage([proposal()]));await Promise.all([one,two]);
 const host=dom(),view=await mountReview(host,{project:'book',proposalController:f.controller,request:()=>{throw Error('unexpected');}});view.destroy();await mountReview(dom(),{project:'book',proposalController:f.controller,request:()=>{throw Error('unexpected');}});assert.equal(f.calls.length,1);assert.equal(f.opened.length,0);
});
test('continuation retains exact cut and rejects drift without merging pages',async()=>{
 const more={http:{method:'GET',url:'/authoring/proposals?project=book&view=queue&cursor=next'}};let drift=false;
 const f=queueFixture(path=>path.includes('cursor=')?queuePage([proposal('U')],drift?'new':'cut'):queuePage([proposal()], 'cut',{pagination:{next_read:more}}));await f.controller.read();drift=true;await assert.rejects(f.controller.more(),/cut changed/);assert.deepEqual(f.controller.snapshot().data.proposals.map(r=>r.id),['T']);assert.equal(f.calls.length,2);
 drift=false;await f.controller.more();assert.deepEqual(f.controller.snapshot().data.proposals.map(r=>r.id),['T','U']);
});
test('partial application and newer candidate use owner reads, never local count/status promotion or selected-version replacement',async()=>{
 let rows=[proposal()],cut='cut';const f=queueFixture(()=>queuePage(rows,cut));await f.controller.read();await f.controller.open('T',{proposalVersion:'V',readHandle:pin('book','T','V')});
 rows=[{...proposal(),edit_count:1}];cut='partial';await f.controller.settled();assert.equal(f.controller.snapshot().data.proposals[0].edit_count,1);
 rows=[proposal('T','NEW')];cut='new';await f.controller.settled();assert.equal(f.controller.snapshot().data.proposals[0].proposal_version,'NEW');assert.equal(f.controller.snapshot().selection.proposalVersion,'V');assert.equal(f.opened.length,1);
});
test('old queued response cannot repaint after invalidation or destroyed project',async()=>{
 let release;const f=queueFixture((path,n)=>n===1?new Promise(resolve=>release=resolve):queuePage([proposal('NEW')]));const updates=[];f.controller.subscribe(value=>updates.push(value.data));const old=f.controller.read();await new Promise(resolve=>setImmediate(resolve));const fresh=f.controller.settled();release(queuePage([proposal('OLD')]));await Promise.all([old,fresh]);assert.deepEqual(f.controller.snapshot().data.proposals.map(r=>r.id),['NEW']);assert.ok(!updates.some(d=>d?.proposals?.some(r=>r.id==='OLD')));
 let last;const g=queueFixture(()=>new Promise(resolve=>last=resolve));let paints=0;g.controller.subscribe(()=>paints++);const pending=g.controller.read();await new Promise(resolve=>setImmediate(resolve));g.controller.destroy();const held=paints;last(queuePage([proposal()]));await pending;assert.equal(paints,held);assert.equal(g.controller.snapshot().data,null);
});
test('project namespace, exact version and duplicate rows refuse before comparison',async()=>{
 for(const row of [{...proposal(),project:'other'}, {...proposal(),read_handle:pin('other','T','V')},{...proposal(),read_handle:pin('book','T','NEW')}]){const f=queueFixture(()=>queuePage([row]));await assert.rejects(f.controller.read());assert.equal(f.opened.length,0);}
 const f=queueFixture(()=>queuePage([proposal(),proposal()]));await assert.rejects(f.controller.read(),/repeats/);await assert.rejects(f.controller.open('T',{proposalVersion:'V',readHandle:pin('book','T','NEW')}),/version/);await assert.rejects(f.controller.open('T'),/exact saved version/);assert.equal(f.opened.length,0);
});
test('legacy provenance opens bounded history for explicit immutable choice, not latest preview',async()=>{
 const host=dom(),f=queueFixture(path=>queuePage([proposal('T','OLD'),proposal('T','NEW')],'history',{view:path.includes('view=history')?'history':'queue'}));const view=await mountReview(host,{project:'book',proposalController:f.controller,request:()=>{throw Error('body');}});await view.showProposals('T');assert.match(f.calls.at(-1),/view=history&turn_id=T/);assert.equal(f.opened.length,0);await host.all().filter(n=>n.tag==='button'&&n.textContent==='Review in manuscript')[0].onclick();assert.equal(f.opened[0][1].proposalVersion,'OLD');
});
test('post-effect queue refresh failure keeps exact selected basis and reports recorded effect without retry',async()=>{
 let failed=false;const f=queueFixture(()=>{if(failed)throw Error('offline');return queuePage([proposal()]);});await f.controller.read();await f.controller.open('T',{proposalVersion:'V',readHandle:pin('book','T','V')});failed=true;assert.equal(await f.controller.settled(),null);assert.equal(f.controller.snapshot().selection.proposalVersion,'V');assert.match(f.statuses.at(-1)[0],/recorded.*unavailable/);assert.equal(f.calls.length,2);assert.equal(f.opened.length,1);
});
test('hidden Review does not repaint, retained note draft/caret/save guard survives queue refresh and resume',async()=>{
 const host=dom(),f=queueFixture(()=>queuePage([proposal()]));let historyCalls=0;const view=await mountReview(host,{project:'book',initialFilter:'notes',proposalController:f.controller,request:async()=>{historyCalls++;return {revision:41,items:[],counts:{},as_of:'notes',total:0};}});await find(host,'New project note').onclick();const note=host.querySelector('textarea');note.value='Keep exact local note';note.oninput();note.focus();note.setSelectionRange(2,6);
 view.setActive(false);const children=host.children;await f.controller.settled();assert.equal(host.children,children);view.setActive(true);await new Promise(resolve=>setImmediate(resolve));assert.equal(host.querySelector('textarea'),note);assert.equal(note.value,'Keep exact local note');assert.equal(document.activeElement,note);assert.equal(note.selectionStart,2);assert.equal(note.selectionEnd,6);assert.equal(historyCalls,1);assert.equal(view.hasDraft,true);
});

// the shell's Review, proposal and conversation-column doors are domain modules (M5 S2 F1)
const workspaceSource=(await import('./helpers/workspace_source.mjs')).workspaceSource();
test('actual workspace Review navigation accepts its void success and opens explicit legacy history without changing session',async()=>{
 const code=workspaceSource.match(/async function openProjectReview\([^\n]+/)[0],seen=[];const open=new Function('views','reviewController',code+';return openProjectReview;')({show:async view=>{seen.push(view);}}, {showProposals:id=>seen.push(id)});await open({turnId:'LEGACY'});assert.deepEqual(seen,['review','LEGACY']);
 const declined=new Function('views','reviewController',code+';return openProjectReview;')({show:async()=>false},{showProposals:()=>{throw Error('dirty navigation refused');}});await declined({turnId:'LEGACY'});
});
test('one project event lifecycle refreshes with visibility guards and is removed on destroy',async()=>{
 class Events{constructor(){this.handlers=new Map();}addEventListener(kind,fn){this.handlers.set(kind,fn);}removeEventListener(kind,fn){if(this.handlers.get(kind)===fn)this.handlers.delete(kind);}fire(kind,arg){this.handlers.get(kind)?.(arg);}}
 const events=new Events(),page=new Events();page.visibilityState='visible';let reads=0;const controller=createProjectReview({project:'book',events,document:page,request:async()=>{reads++;return queuePage([proposal()]);},onReviewProposal:()=>{}});
 await controller.read();events.fire('focus');page.fire('visibilitychange');await new Promise(resolve=>setImmediate(resolve));assert.equal(reads,1);
 page.visibilityState='hidden';events.fire('storage',{key:'laplace:proposal-update:book'});events.fire('laplace-workspace-reconnected');await new Promise(resolve=>setImmediate(resolve));assert.equal(reads,1);
 page.visibilityState='visible';events.fire('storage',{key:'other-project'});assert.equal(reads,1);events.fire('storage',{key:'laplace:proposal-update:book'});await new Promise(resolve=>setImmediate(resolve));assert.equal(reads,2);controller.destroy();assert.equal(events.handlers.size,0);assert.equal(page.handlers.size,0);
});


test('Review card labels belong to candidate turn, conversation is provenance, page rows are not total changes',async()=>{
 const host=dom(),rows=[{...proposal('TITLE','V-title'),proposal_label:'Review the manuscript title',label_basis:'stored-turn-context',conversation_title:'Earlier paragraph conversation',edit_count:2,turn_ts:'2026-10-08T17:00:00Z'},{...proposal('OLDER','V-old'),proposal_label:'Review chapter introduction',label_basis:'stored-turn-context',conversation_title:'Earlier paragraph conversation',edit_count:35,label_truncated:true}];
 const more={http:{method:'GET',url:'/authoring/proposals?project=book&view=queue&cursor=more'}},f=queueFixture(()=>queuePage(rows,'cut',{pagination:{next_read:more}}));await mountReview(host,{project:'book',proposalController:f.controller,request:()=>{throw Error('unneeded body');}});
 assert.deepEqual(host.all().filter(n=>n.tag==='h3').map(n=>n.textContent),['Review the manuscript title','Review chapter introduction']);
 assert.ok(find(host,'Proposed · 2 candidates inspected'));assert.ok(find(host,'Inspect more proposal candidates'));assert.match(host.textContent,/Conversation: Earlier paragraph conversation/);assert.match(host.textContent,/Stored context label truncated/);assert.match(host.textContent,/total unknown/);assert.equal(f.calls.length,1);
});


test('actual successful comparison opening temporarily hides dock; stale response preserves it',async()=>{
 const start=workspaceSource.indexOf('  async function reviewProposal('),end=workspaceSource.indexOf('const selectedVersion=preview.proposal_version;',start),code=workspaceSource.slice(start,end)+'return preview;}',calls=[],walk={};
 const make=current=>new Function('bindings',`const {project,manuscriptReady,sourceWindow,api,proposalReadURL,openSession,currentView}=bindings;const manuscript={ready:manuscriptReady,sourceWindow},discussion={open:openSession},views={current:()=>currentView};let proposalReviewGeneration=0;${code};return reviewProposal;`)({project:'book',manuscriptReady:async()=>walk,sourceWindow:()=>({walk:current?walk:{}}),api:async()=>({proposal_version:'V'}),proposalReadURL:()=>'/exact',openSession:(...args)=>calls.push(args),currentView:'manuscript'});
 await make(true)('T',{proposalVersion:'V',readHandle:pin('book','T','V')});assert.deepEqual(calls,[[false,{remember:false}]]);calls.length=0;await make(false)('T',{proposalVersion:'V',readHandle:pin('book','T','V')});assert.deepEqual(calls,[]);
});
test('existing dock collapse does not clear conversation draft or attached selection or stored preference',()=>{
 const code=workspaceSource.slice(workspaceSource.indexOf('function openSession(open,'),workspaceSource.indexOf('\n  let focusRestore=null;')),draft={text:'Keep unsent words',selection:{files:['chapter.tex']}},calls=[];
 const session={setLibrary:value=>calls.push(['library',value]),expand:value=>calls.push(['expand',value]),catalogueOpened:()=>{throw Error('no provider observation on collapse');}},root={classList:{toggle:(...args)=>calls.push(args)}},host={};
 const close=new Function('session','root','$','localStorage','window','Event',"const discussion={session:()=>session},ui={root,$},SESSION_OPEN_KEY='laplace:workspace:session-open';"+code+';return openSession;')(session,root,selector=>selector==='[data-session]'?host:{setAttribute:(...args)=>calls.push(args)},{setItem:()=>{throw Error('temporary reading must not replace preference');}},{dispatchEvent(){}},class{});
 close(false,{remember:false});assert.equal(host.hidden,true);assert.deepEqual(draft,{text:'Keep unsent words',selection:{files:['chapter.tex']}});assert.deepEqual(calls.slice(0,2),[['library',false],['expand',false]]);
});


test('default Review card shows useful content while exact machine basis stays expandable',async()=>{
 const host=dom(),opened=[],f=queueFixture(()=>queuePage([{...proposal(),proposal_label:'Revise the title',label_basis:'stored-turn-context',conversation_title:'Earlier paragraph discussion',turn_ts:'2026-10-08T17:00:00Z'}]));await mountReview(host,{project:'book',proposalController:f.controller,onReadTurn:id=>opened.push(id),request:()=>{throw Error('unneeded');}});
 const row=host.all().find(n=>n.tag==='article'),defaultText=row.children.filter(n=>n.tag!=='details').map(n=>n.textContent).join(' ');assert.match(defaultText,/Revise the title/);assert.match(defaultText,/chapter.tex/);assert.ok(!defaultText.includes('stored-turn-context'));assert.ok(!defaultText.includes('2026-10-08T17:00:00Z'));assert.ok(!defaultText.includes('Earlier paragraph discussion'));
 const details=row.querySelector('details');assert.equal(details.open,undefined);assert.match(details.textContent,/Label basis: stored-turn-context/);await find(details,'Read originating turn').onclick();assert.deepEqual(opened,['T']);assert.equal(f.calls.length,1);
});
test('an empty partial or unavailable owner page cannot claim the whole queue is empty',async()=>{
 const more={http:{method:'GET',url:'/authoring/proposals?project=book&view=queue&cursor=more'}};
 for(const extra of [{pagination:{next_read:more}},{coverage:{unavailable_candidate_records:['missing']}}]){const host=dom(),f=queueFixture(()=>queuePage([],'cut',extra));await mountReview(host,{project:'book',proposalController:f.controller,request:()=>{throw Error('unneeded');}});assert.ok(!host.textContent.includes('No manuscript changes are waiting'));assert.match(host.textContent,/on this inspected page|records are unavailable/);}
});


test('unavailable earlier-page records remain visible in inspected coverage after continuation',async()=>{
 const more={http:{method:'GET',url:'/authoring/proposals?project=book&view=queue&cursor=more'}},host=dom(),f=queueFixture((path,n)=>n===1?queuePage([],'cut',{pagination:{next_read:more},coverage:{unavailable_candidate_records:['missing']}}):queuePage([]));await mountReview(host,{project:'book',proposalController:f.controller,request:()=>{throw Error('unneeded');}});await find(host,'Inspect more proposal candidates').onclick();assert.deepEqual(f.controller.snapshot().data.coverage.unavailable_candidate_records,['missing']);assert.ok(!host.textContent.includes('No manuscript changes are waiting'));
});


test('queue discovery does not advertise recorded-ready metadata as current applicability',()=>{
 assert.equal(proposalStandingLabel({proposal_state:'ready'}),'Awaiting exact comparison');
 assert.equal(proposalStandingLabel({proposal_state:'blocked'}),'Needs reconciliation');
});

// M5 C9: Review carries Proposed, Versions, Comments, Notes and Closed; saved manuscript edits are Activity records
test('Review tabs carry no saved-edit category and point to Activity for saved manuscript edits',async()=>{
 const {host}=await fixture();const tabs=host.all().filter(n=>n.tag==='button'&&n.attrs.role==='tab').map(n=>n.textContent);
 assert.ok(tabs.some(t=>t.startsWith('Proposed')));assert.ok(tabs.some(t=>t.startsWith('Versions')));assert.ok(tabs.some(t=>t.startsWith('Comments')));assert.ok(tabs.some(t=>t.startsWith('Notes')));assert.ok(tabs.some(t=>t.startsWith('Closed')));
 assert.ok(!tabs.some(t=>/Your changes|Saved manuscript edit/.test(t)));assert.match(host.textContent,/Saved manuscript edits are recorded in Activity/);
});
