import {beforeEach,test} from 'node:test';
import assert from 'node:assert/strict';
import {renderMaterialObservation,materialReadURL,renderInertMarkdown,markdownReading,ReadingLimitError} from '../src/laplace/web/static_shared/workspace-material-observation.mjs';
class Node{
 constructor(tag='div'){this.tag=tag;this.children=[];this._text='';this.isConnected=true;this.className='';this.dataset={};}
 set textContent(value){this._text=String(value??'');this.children=[];}get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}setAttribute(){}all(){return [this,...this.children.flatMap(x=>x.all())];}
}
beforeEach(()=>{globalThis.document={createElement:tag=>new Node(tag)};});
const button=(host,label)=>host.all().find(x=>x.tag==='button'&&x.textContent===label);
const handle=url=>({http:{method:'GET',url}});
const observation=(content,next)=>({target:{owner:'repository',repository:'owner',path:'source.md'},current_revision:'digest',currentness:'UNBOUND',units:'Unicode characters',owner_result:{content},...(next?{read_handle:handle(next)}:{})});
// real-shaped owner pages: offsets are the owner's coordinates (here Unicode scalars), not JS code units
const paged=(content,offset,next,url)=>({...observation(content,url),owner_result:{content,offset,next_offset:next}});
test('inert Markdown renders a table, code and links as plain nodes and never creates a fetching or executable node',()=>{
 const text=['# Purpose','','A **bold** claim with `code`, a [link](https://example.test/x) and a [local one](docs/a.md).','','| Fact | Owner |','|---|---|','| Sent | delivery |','| Applied | adoption |','',
  '- one','- two','','```js','<script>alert(1)</script>','```','','![chart](https://example.test/a.png)','','<iframe src="https://example.test"></iframe>','<script>fetch("/x")</script>'].join('\n');
 const root=renderInertMarkdown(text),tags=root.all().map(node=>node.tag);
 for(const forbidden of ['script','img','iframe','style','link','object','embed','video','audio','source'])assert.ok(!tags.includes(forbidden),forbidden);
 assert.ok(tags.includes('table')&&tags.filter(tag=>tag==='tr').length===3&&tags.includes('th')&&tags.includes('td'));
 assert.ok(tags.includes('h4')&&tags.includes('strong')&&tags.includes('code')&&tags.includes('ul')&&tags.includes('pre'));
 assert.equal(tags.filter(tag=>tag==='a').length,1);
 assert.match(root.textContent,/Image not loaded: chart/);assert.match(root.textContent,/HTML block not rendered: 2 lines/);
 assert.match(root.textContent,/\(https:\/\/example\.test\/x\)/);assert.match(root.textContent,/docs\/a\.md; not opened from here/);
 assert.match(root.textContent,/<script>alert\(1\)<\/script>/);   // code stays visible text, never markup
});
test('hostile under-cap nested quotes are bounded and kept as visible text; ordinary nested quotes and tables still render',()=>{
 const hostile='>'.repeat(20000)+' deepest words';
 assert.ok(hostile.length<262144);
 const root=renderInertMarkdown(hostile),quotes=root.all().filter(node=>node.tag==='blockquote').length;
 assert.ok(quotes>=1&&quotes<=9,String(quotes));
 assert.match(root.textContent,/Quote nesting deeper than 8 levels is shown as text here/);assert.match(root.textContent,/deepest words/);
 const ordinary=renderInertMarkdown('> outer\n> > inner\n\n| A | B |\n|---|---|\n| 1 | 2 |');
 assert.equal(ordinary.all().filter(node=>node.tag==='blockquote').length,2);assert.ok(ordinary.all().some(node=>node.tag==='table'));
 const host=new Node();
 renderMaterialObservation(host,{...observation(hostile),currentness:'CURRENT',consumed_revision:'digest'},{request:async()=>assert.fail('No read')});
 assert.match(host.textContent,/deepest words/);assert.match(host.textContent,/Quote nesting deeper than 8 levels/);
 button(host,'Raw').onclick();
 assert.equal(host.all().find(node=>node.tag==='pre'&&node.className==='material-source-reading').textContent,hostile);
});
test('bounded recognition: hostile near-cap inline and block families render literally within a deterministic work bound',()=>{
 const cap=262144-64;
 const families={brackets:'['.repeat(cap),angles:'<'.repeat(cap),images:'!['.repeat(cap/2),links:'[a]('.repeat(cap/4),
  ticks:'a'+'`'.repeat(cap/2)+'x'+'``'.repeat(cap/4-16),stars:'a'+'*'.repeat(cap-1),unders:'a'+'_'.repeat(cap-1),tails:'[x](http://a '.repeat(cap/16),
  heading:'#'+' '.repeat(cap-2)+'x',rule:'- '.repeat(cap/2-2)+'x',table:'|'+' '.repeat(cap/2)+'|\n|'+' -'.repeat(cap/8)+' x|'};
 for(const [name,text] of Object.entries(families)){
  assert.ok(text.length<=262144,name);
  const budget={work:0,nodes:0};
  const root=renderInertMarkdown(text,{budget});
  assert.ok(budget.work<=12*text.length+64,name+' work '+budget.work);assert.ok(budget.nodes<64,name+' nodes '+budget.nodes);
  for(const forbidden of ['script','img','iframe','style','a'])assert.ok(!root.all().some(node=>node.tag===forbidden),name+' '+forbidden);
  assert.ok(root.textContent.length>0,name);
 }
});
test('dense valid structures share one aggregate node budget and fall back to exact Raw with a notice; ordinary 65 KB tables and quotes still render',()=>{
 const dense='- a\n'.repeat(60000);
 assert.throws(()=>renderInertMarkdown(dense),ReadingLimitError);
 const nested='> > '+'- q\n> > '.repeat(30000);
 assert.throws(()=>renderInertMarkdown(nested),ReadingLimitError);
 const host=new Node();renderMaterialObservation(host,{...observation(dense),currentness:'CURRENT'},{request:async()=>assert.fail('No read')});
 assert.match(host.textContent,/too large or too dense/);assert.ok(!host.all().some(node=>node.tag==='li'));
 assert.equal(host.all().find(node=>node.tag==='pre'&&node.className==='material-source-reading').textContent,dense);
 const rows=Array.from({length:2000},(_,n)=>'| row '+n+' | value '+n+' | owner |').join('\n');
 const ordinary='# Report\n\n> a quoted **note** with `code`\n> > nested reply\n\n| Row | Value | Owner |\n|---|---|---|\n'+rows+'\n';
 assert.ok(ordinary.length>60000);
 const read=renderInertMarkdown(ordinary);
 assert.equal(read.all().filter(node=>node.tag==='tr').length,2001);assert.equal(read.all().filter(node=>node.tag==='blockquote').length,2);
 assert.ok(read.all().some(node=>node.tag==='strong')&&read.all().some(node=>node.tag==='code')&&read.all().some(node=>node.tag==='h4'));
});
test('initial and clicked Reading share one eligibility: an over-limit or partial text stays Raw with a notice even when Reading is pressed',()=>{
 const host=new Node(),big='x'.repeat(262145);host.append(markdownReading(big));
 assert.match(host.textContent,/longer than the rendered-reading limit/);
 button(host,'Reading').onclick();
 assert.match(host.textContent,/longer than the rendered-reading limit/);assert.ok(!host.all().some(node=>node.className==='markdown-reading'));
 const partial=new Node();partial.append(markdownReading('# t',{complete:false}));button(partial,'Reading').onclick();
 assert.ok(!partial.all().some(node=>node.tag==='h4'));assert.match(partial.textContent,/bounded page/);
});
test('complete reading starts only at the exact first page and joins only contiguous, progressing, unchanged owner pages',async()=>{
 const first=paged('# Head π🌱 ',0,10,'/p1'),second=paged('tail é中',10,null);
 const host=new Node(),calls=[];renderMaterialObservation(host,first,{request:async url=>{calls.push(url);return second;}});
 await button(host,'Read the complete document').onclick();
 assert.deepEqual(calls,['/p1']);assert.match(host.textContent,/π🌱 tail é中/);assert.ok(host.all().some(node=>node.tag==='h4'));
 const later=new Node();renderMaterialObservation(later,paged('middle',10,20,'/p2'),{request:async()=>assert.fail('no join from a later page')});
 assert.equal(button(later,'Read the complete document'),undefined);assert.match(later.textContent,/stays paged/);
 for(const [label,reply,expected] of [
  ['old offset fixture',paged('tail',18,null),/does not continue/],
  ['empty nonterminal',paged('',10,10,'/p1'),/no progress/],
  ['repeated page',paged('# Head π🌱 ',0,10,'/p1'),/does not continue/],
  ['moved',{...paged('tail',10,null),current_revision:'changed'},/Source changed/],
  ['truncated terminal',{...paged('tail',10,null),owner_result:{content:'tail',offset:10,next_offset:14,truncated:true}},/issued no continuation/],
  ['final over limit',paged('y'.repeat(262144),10,null),/longer than the rendered-reading limit/]]){
  const view=new Node();renderMaterialObservation(view,first,{request:async()=>reply});
  await button(view,'Read the complete document').onclick();
  assert.match(view.textContent,expected,label);assert.match(view.textContent,/Head π/,label);assert.ok(!view.all().some(node=>node.tag==='h4'),label);
 }
 const empty=new Node();renderMaterialObservation(empty,first,{request:async()=>paged('',10,null)});
 await button(empty,'Read the complete document').onclick();assert.ok(empty.all().some(node=>node.tag==='h4'),'a genuinely empty terminal page completes');
});
// Artifact pages: the owner's UTF-8 byte offsets, size_bytes and terminal fields (complete, next_offset)
const artifact=(content,offset,next,size,url,extra={})=>({target:{owner:'artifact',project:'p',path:'doc.md',scope:'project'},current_revision:'digest',currentness:'UNBOUND',
 owner_result:{content,offset,next_offset:next,size_bytes:size,complete:next==null,...extra},...(url?{read_handle:handle(url)}:{})});
test('owner extents: Artifact joins verify UTF-8 spans, the unchanged size and terminal fields; scalar pages refuse a claimed jump',async()=>{
 const head='# T π🌱\r\n',tail='| A |\r\n|---|\r\n| 1 |';
 assert.equal(new TextEncoder().encode(head).length,12);assert.equal(new TextEncoder().encode(tail).length,19);
 const first=artifact(head,0,12,31,'/a1'),last=artifact(tail,12,null,31);
 const host=new Node();renderMaterialObservation(host,first,{request:async()=>last});
 await button(host,'Read the complete document').onclick();
 assert.ok(host.all().some(node=>node.tag==='table'),'exact UTF-8 spans join');assert.match(host.textContent,/π🌱/);
 for(const [label,start,reply,expected] of [
  ['UTF-16 claim',artifact(head,0,9,31,'/a1'),artifact(tail,9,null,31),/does not end where/],
  ['byte jump',first,artifact(tail,12,40,31,'/a2'),/does not end where/],
  ['changed size',first,artifact(tail,12,null,32),/Source changed/],
  ['short of size',artifact(head,0,12,40,'/a1'),artifact(tail,12,null,40),/do not add up/],
  ['incomplete terminal',first,artifact(tail,12,null,31,null,{complete:false}),/issued no continuation/],
  ['remaining suffix',first,artifact(tail,12,31,31),/issued no continuation/]]){
  const view=new Node();renderMaterialObservation(view,start,{request:async()=>reply});
  await button(view,'Read the complete document').onclick();
  assert.match(view.textContent,expected,label);assert.ok(!view.all().some(node=>node.tag==='table'),label);assert.match(view.textContent,/# T π/,label);
 }
 const blank=new Node();renderMaterialObservation(blank,artifact('',0,null,0),{request:async()=>assert.fail('no read')});
 assert.ok(blank.all().some(node=>node.className==='markdown-reading'),'a valid empty complete Artifact reads whole');assert.doesNotMatch(blank.textContent,/stays as exact text/);
 const single=new Node();renderMaterialObservation(single,artifact('# One',0,null,9),{request:async()=>assert.fail('no read')});
 assert.ok(!single.all().some(node=>node.className==='markdown-reading'));assert.match(single.textContent,/reported document size/);assert.equal(button(single,'Read the complete document'),undefined);
 const suffix=new Node();renderMaterialObservation(suffix,artifact('# One',0,5,9),{request:async()=>assert.fail('no read')});
 assert.match(suffix.textContent,/issued no continuation/);assert.ok(!suffix.all().some(node=>node.className==='markdown-reading'));
 const ended=new Node();renderMaterialObservation(ended,artifact('# T\n',0,4,4,'/a1'),{request:async()=>artifact('',4,null,4)});
 await button(ended,'Read the complete document').onclick();assert.ok(ended.all().some(node=>node.tag==='h4'),'an exact empty terminal page completes');
 const scalar=new Node();renderMaterialObservation(scalar,paged('# Head π🌱 ',0,11,'/p1'),{request:async()=>paged('tail',11,null)});
 await button(scalar,'Read the complete document').onclick();assert.match(scalar.textContent,/does not end where/);assert.ok(!scalar.all().some(node=>node.tag==='h4'));
 const unknown=new Node();renderMaterialObservation(unknown,{...paged('# Head',0,6,'/p1'),units:'pages'},{request:async()=>assert.fail('no read')});
 await button(unknown,'Read the complete document').onclick();assert.match(unknown.textContent,/no unit/);
});
// Root correction fe1d8bf6 / C finding 1: Complete and Read more on one connected presenter share one sequence fence
test('connected Complete and Read more: a late success or rejection of the superseded read never rewrites the newer observation',async()=>{
 const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
 const first={...paged('# Head π🌱 ',0,10,'/p1'),restart_read:handle('/restart')},second=paged('tail é中',10,null);
 for(const order of ['complete-first','more-first'])for(const outcome of ['reject','resolve']){
  const host=new Node(),pending=[];let errors=0,observations=0;
  renderMaterialObservation(host,first,{request:()=>{const d=deferred();pending.push(d);return d.promise;},onReadError:()=>errors++,onObservation:()=>observations++});
  const whole=button(host,'Read the complete document'),more=button(host,'Read more source'),label=order+' '+outcome;
  const earlier=(order==='complete-first'?whole:more).onclick(),later=(order==='complete-first'?more:whole).onclick();
  assert.equal(pending.length,2,label);
  pending[1].resolve(second);await later;
  if(outcome==='reject')pending[0].reject(Error('superseded owner read failed'));else pending[0].resolve(order==='complete-first'?second:paged('stale page',10,null));
  await earlier;
  assert.equal(errors,0,label);assert.ok(!host.all().some(node=>node.className==='error'),label);
  assert.doesNotMatch(host.textContent,/superseded owner read failed|stale page|latest source read failed/,label);
  if(order==='complete-first'){assert.match(host.textContent,/tail é中/,label);assert.ok(!host.all().some(node=>node.tag==='h4'),label);assert.equal(observations,2,label);}
  else{assert.ok(host.all().some(node=>node.tag==='h4'),label);assert.match(host.textContent,/π🌱 tail é中/,label);assert.equal(observations,1,label);}
 }
});
// Root joined correction (source-03): a Cancel is bound to its own GET; an older Cancel never discards the newer pending read
test('two overlapping Material reads: Cancel on the older read aborts only its GET and leaves the newer pending read and its page; Add to Literature is a guarded effect with no Cancel row',async()=>{
 const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
 const first={...paged('# Head π🌱 ',0,10,'/p1'),restart_read:handle('/restart')},second=paged('tail é中',10,null);
 const host=new Node(),pending=[],signals=[];let errors=0;
 renderMaterialObservation(host,first,{request:(_url,_payload,options)=>{const d=deferred();pending.push(d);signals.push(options?.signal||null);return d.promise;},onReadError:()=>errors++});
 const whole=button(host,'Read the complete document').onclick(),more=button(host,'Read more source').onclick();
 assert.equal(pending.length,2);const cancels=host.all().filter(x=>x.tag==='button'&&x.textContent==='Cancel this read');assert.equal(cancels.length,2,'each pending read has its own Cancel');
 cancels[0].onclick();assert.equal(signals[0]?.aborted,true,'Cancel A aborts only A');assert.equal(signals[1]?.aborted,false,'B keeps its own GET');
 pending[1].resolve(second);await more;assert.match(host.textContent,/tail é中/,'the newer read B still paints its page');
 pending[0].reject(Error('aborted A'));await whole;assert.equal(errors,0);assert.ok(!host.all().some(node=>node.className==='error'));assert.doesNotMatch(host.textContent,/aborted A/);
 const lit=new Node();let added=0;renderMaterialObservation(lit,{...observation('Plain text'),owner_result:{content:'Plain text',literature:{project:'p',payload:{original:{artifact_id:'ART-1'}}}}},{request:async()=>assert.fail('no read'),onAddToLiterature:()=>{added++;}});
 await button(lit,'Add to Literature').onclick();assert.equal(added,1);assert.equal(button(lit,'Cancel this read'),undefined,'a guarded effect is not a cancellable read');
});
test('mouse reading: provenance sits under Details, the notice and complete action lead the page, and a joined reading drops its terminal continuation controls',async()=>{
 const host=new Node(),calls=[];
 renderMaterialObservation(host,{...paged('# Title\n\nfirst ',0,15,'/p1'),currentness:'CURRENT',consumed_revision:'digest'},{request:async url=>{calls.push(url);return paged('second',15,null);}});
 assert.equal(host.children[0].className,'material-currentness');
 const details=host.children[1],bar=host.children[2],order=host.children.map(node=>node.className);
 assert.equal(details.tag,'details');assert.equal(details.children[0].textContent,'Details');
 assert.match(details.textContent,/Source: owner=repository/);assert.match(details.textContent,/Consumed: digest/);assert.match(details.textContent,/Current: digest/);assert.match(details.textContent,/availability and project membership only/);
 assert.equal(bar.className,'material-reading-bar');assert.ok(order.indexOf('material-reading-bar')<order.indexOf('material-markdown'),'controls lead the page');
 assert.match(bar.textContent,/Bounded text page/);assert.ok(bar.all().includes(button(host,'Read the complete document')),'the complete action is above the first page');
 assert.deepEqual(calls,[],'nothing is read until the person asks');
 const more=button(host,'Read more source');assert.ok(more&&!more.hidden);
 await button(host,'Read the complete document').onclick();
 assert.deepEqual(calls,['/p1']);assert.ok(host.all().some(node=>node.tag==='h4'),'the joined document is the formatted reading');
 assert.ok(button(host,'Reading')&&button(host,'Raw'),'Reading and Raw come with the joined document');
 assert.equal(button(host,'Read the complete document'),undefined,'the consumed complete action leaves');assert.equal(more.hidden,true,'the consumed paging action leaves');
 assert.match(bar.textContent,/Complete document at this source revision/);assert.doesNotMatch(bar.textContent,/Bounded text page/);
});
test('the ordinary Read entry starts the same bounded join once and leads with the formatted document; a late cancelled read never takes newer focus',async()=>{
 const host=new Node(),calls=[];
 renderMaterialObservation(host,paged('# Title\n\nfirst ',0,15,'/p1'),{completeReading:true,request:async url=>{calls.push(url);return paged('second',15,null);}});
 for(let n=0;n<4;n++)await new Promise(resolve=>setTimeout(resolve,0));
 assert.deepEqual(calls,['/p1'],'one join, started once');assert.ok(host.all().some(node=>node.tag==='h4'));assert.equal(button(host,'Read the complete document'),undefined);
 assert.ok(!host.all().some(node=>node.tag==='button'&&node.textContent==='Read more source'&&!node.hidden),'no stale paging control remains');
 for(const [newer,expected] of [[true,[]],[false,['opener']]]){
  const view=new Node(),other=new Node('button'),focused=[];let fail;
  renderMaterialObservation(view,paged('# T\n\nfirst',0,10,'/q1'),{request:()=>new Promise((resolve,reject)=>{fail=reject;})});
  const opener=button(view,'Read the complete document');opener.focus=()=>focused.push('opener');
  const pending=opener.onclick(),cancel=button(view,'Cancel this read');
  globalThis.document.activeElement=cancel;cancel.onclick();
  if(newer)globalThis.document.activeElement=other;   // the person has since focused something else
  fail(Error('aborted'));await pending;
  assert.deepEqual(focused,expected,newer?'a late focus return never takes newer focus':'focus returns while nothing else owns it');
 }
});
test('the owners reader path (document label) keeps the complete action above the page, starts a next, first or joined page at its top and offers Back to the first page',async()=>{
 const host=new Node(),calls=[],scrolls=[];host.scrollIntoView=options=>scrolls.push(options.block);
 const first=paged('# Title\n\nfirst ',0,15,'/p1');
 renderMaterialObservation(host,first,{documentLabel:'docs/identity.md',initialHandle:handle('/p0'),request:async url=>{calls.push(url);return url==='/p0'?first:paged('second',15,null);}});
 const order=host.children.map(node=>node.className),bar=host.children[order.indexOf('material-reading-bar')];
 assert.equal(host.children[0].tag,'h3');assert.ok(bar&&order.indexOf('material-reading-bar')<order.indexOf('material-markdown'),'controls lead the page');
 assert.ok(bar.all().includes(button(host,'Read the complete document')),'the complete action needs no scrolling through the first page');assert.match(bar.textContent,/Bounded text page/);
 assert.equal(button(host,'Back to the first page'),undefined,'Back is offered only after a later page was reached here');
 await button(host,'Read more source').onclick();
 assert.deepEqual(calls,['/p1']);assert.deepEqual(scrolls,['start'],'the next page starts at its top');
 const back=button(host,'Back to the first page');assert.ok(back,'Back is in reach on a later page');
 await back.onclick();
 assert.deepEqual(calls,['/p1','/p0']);assert.deepEqual(scrolls,['start','start']);assert.equal(button(host,'Back to the first page'),undefined);
 await button(host,'Read the complete document').onclick();
 assert.deepEqual(calls,['/p1','/p0','/p1']);assert.ok(host.all().some(node=>node.tag==='h4'),'the joined document is the formatted reading');
 assert.deepEqual(scrolls,['start','start','start'],'the joined reading starts at its top, with Reading and Raw in reach');
 assert.ok(button(host,'Reading')&&button(host,'Raw'));assert.equal(button(host,'Read the complete document'),undefined);
 assert.ok(!host.all().some(node=>node.tag==='button'&&node.textContent==='Read more source'&&!node.hidden),'no stale paging control remains');
});
// owners-control-05: the shared MATERIAL presenter (not the System owners reader, which has its own mounted test)
test('Material read notices sit in the reading bar: a local limit keeps the valid page and its standing, an owner failure says why beside the complete action, and a newer notice replaces the earlier one',async()=>{
 const host=new Node(),calls=[],big='x'.repeat(262200);
 renderMaterialObservation(host,{...paged(big,0,262200,'/p1'),currentness:'CURRENT',consumed_revision:'digest'},{request:async url=>{calls.push(url);return paged('never',262200,null);}});
 const bar=host.children.find(node=>node.className==='material-reading-bar'),standing=host.children[0].textContent;
 await button(host,'Read the complete document').onclick();
 assert.deepEqual(calls,[],'the local limit refuses before any read');
 const limit=bar.all().find(node=>node.className==='muted reading-notice');assert.ok(limit,'the limit notice is in the reading bar');assert.match(limit.textContent,/longer than the rendered-reading limit/);
 assert.equal(host.children[0].textContent,standing,'the valid observation keeps its standing');assert.ok(bar.all().includes(button(host,'Read the complete document')),'the complete action stays beside the notice');
 assert.equal(host.all().find(node=>node.tag==='pre'&&node.className==='material-source-reading').textContent,big,'the valid page is kept');
 const failed=new Node();renderMaterialObservation(failed,paged('# T\n\nfirst',0,10,'/q1'),{request:async()=>paged('gap',99,null)});
 const top=failed.children.find(node=>node.className==='material-reading-bar');
 await button(failed,'Read the complete document').onclick();
 assert.ok(top.all().some(node=>node.className==='error'&&/does not continue where the previous one ended/.test(node.textContent)),'the owner failure is in the reading bar');
 const order=failed.children.map(node=>node.className);assert.ok(order.indexOf('material-reading-bar')<order.indexOf('material-markdown'),'above the text');
 await button(failed,'Read the complete document').onclick();
 assert.equal(top.all().filter(node=>node.className==='error'&&!node.hidden).length,1,'one owned notice: the newer replaces the earlier');
});
test('a local reading limit keeps the valid observation and reader eligibility; a real current owner failure reports, keeps the page and offers restart',async()=>{
 const first={...paged('# Head π🌱 ',0,10,'/p1'),restart_read:handle('/restart')};
 let errors=0;const host=new Node();
 renderMaterialObservation(host,first,{request:async()=>paged('y'.repeat(262144),10,null),onReadError:()=>errors++});
 const standing=host.children[0].textContent;
 await button(host,'Read the complete document').onclick();
 assert.equal(errors,0);assert.match(host.textContent,/longer than the rendered-reading limit/);assert.ok(!host.all().some(node=>node.className==='error'));
 assert.ok(host.all().some(node=>node.className==='muted reading-notice'));assert.equal(host.children[0].textContent,standing);
 assert.equal(button(host,'Restart source observation'),undefined);assert.ok(button(host,'Read more source'));assert.match(host.textContent,/Head π/);
 const failed=new Node();let failures=0;
 renderMaterialObservation(failed,first,{request:async()=>{throw Error('owner transport refused');},onReadError:()=>failures++});
 await button(failed,'Read the complete document').onclick();
 assert.equal(failures,1);assert.match(failed.textContent,/owner transport refused/);assert.ok(failed.all().some(node=>node.className==='error'));
 assert.match(failed.children[0].textContent,/latest source read failed/);assert.ok(button(failed,'Restart source observation'));assert.match(failed.textContent,/Head π/);
});
// The reached connected Material card itself (workspace-material.mjs mountSharedReferences), mounted on the existing html_dom
// double with owner-shaped material-references replies: its real Prepare reader and Adopt controls are observed.
test('mounted Material card: local limit keeps reader/Adopt, a stale Complete rejection keeps the newer reader state, a current failure disarms and offers restart',async()=>{
 const {installHTMLDocument}=await import('./helpers/html_dom.mjs');
 const dom=installHTMLDocument();
 try{
  const {mountSharedReferences}=await import('../src/laplace/web/static_shared/workspace-material.mjs');
  const target={owner:'repository',repository:'repo',path:'docs/guide.md'};
  const row={id:'MAT-1',target,currentness:'CHANGED_INPUT',consumed_revision:'sha256:old',current_revision:'sha256:new',revision:'R1'};
  const source=extra=>({id:'MAT-1',target,currentness:'CHANGED_INPUT',consumed_revision:'sha256:old',current_revision:'sha256:new',revision:'R2',
   units:'Unicode characters',restart_read:{http:{method:'GET',url:'/restart'}},...extra});
  const first=source({owner_result:{content:'# Head π🌱 ',offset:0,next_offset:10},read_handle:{http:{method:'GET',url:'/next'}}});
  let next=async()=>assert.fail('no continuation expected');
  const request=async(url,payload)=>{if(payload!==undefined)assert.fail('the card never writes in this case: '+url);
   if(url.includes('view=source'))return structuredClone(first);
   if(url.startsWith('/projects/material-references'))return {revision:'LIST-1',owners:{repositories:[{id:'repo',label:'repo',available:true}]},references:[structuredClone(row)],total:1,next_offset:null};
   if(url==='/next')return next();
   throw Error('unexpected '+url);};
  const host=document.createElement('section');document.body.append(host);
  await mountSharedReferences(host,{project:'p',request});
  const card=host.querySelector('article');assert.ok(card,'the linked card is mounted');
  const control=label=>card.querySelectorAll('button').find(node=>node.textContent===label);
  const inspect=async()=>{await control('Inspect docs/guide.md').click();
   assert.equal(control('Prepare text-only reader').disabled,false);assert.equal(control('Adopt inspected revision').disabled,false);};
  // 1. a local presentation limit after a valid observation leaves reader and Adopt eligibility intact
  await inspect();
  next=async()=>source({owner_result:{content:'y'.repeat(262144),offset:10,next_offset:null}});
  await control('Read the complete document').click();
  assert.match(card.textContent,/longer than the rendered-reading limit/);assert.doesNotMatch(card.textContent,/Read failed/);
  assert.equal(control('Prepare text-only reader').disabled,false);assert.equal(control('Adopt inspected revision').disabled,false);
  // 2. a superseded Complete that rejects after the newer Read more succeeded keeps the newer reader state
  await inspect();
  const waits=[];next=()=>new Promise((resolve,reject)=>waits.push({resolve,reject}));
  const whole=control('Read the complete document').click(),more=control('Read more source').click();
  assert.equal(waits.length,2);
  waits[1].resolve(source({revision:'R3',owner_result:{content:'tail é中',offset:10,next_offset:null}}));await more;
  waits[0].reject(Error('superseded complete read failed'));await whole;
  assert.match(card.textContent,/tail é中/);assert.doesNotMatch(card.textContent,/superseded complete read failed|Read failed/);
  assert.equal(control('Prepare text-only reader').disabled,false);assert.equal(control('Adopt inspected revision').disabled,true);
  // 3. a current owner transport failure retains the page, disarms reader and Adopt, and offers the issued restart
  await inspect();
  next=async()=>{throw Error('owner transport refused');};
  await control('Read the complete document').click();
  assert.match(card.textContent,/owner transport refused/);assert.match(card.textContent,/Read failed/);assert.match(card.textContent,/Head π/);
  assert.equal(control('Prepare text-only reader').disabled,true);assert.equal(control('Adopt inspected revision').disabled,true);
  assert.ok(control('Restart source observation'),'the issued restart is offered');
 }finally{dom.restore();}
});
test('a complete linked Markdown source reads rendered by default, says membership only, and Raw keeps the exact text',()=>{
 const host=new Node(),text='# Title\n\n| A | B |\n|---|---|\n| 1 | 2 |';
 renderMaterialObservation(host,{...observation(text),currentness:'CURRENT',consumed_revision:'digest'},{request:async()=>assert.fail('No read')});
 assert.ok(host.all().some(node=>node.tag==='table'));
 assert.match(host.textContent,/availability and project membership only\. It is not a produced Work result/);
 button(host,'Raw').onclick();
 const raw=host.all().find(node=>node.tag==='pre'&&node.className==='material-source-reading');
 assert.equal(raw.textContent,text);assert.ok(!host.all().some(node=>node.tag==='table'));
});
test('a bounded Markdown page stays text until its own same-revision continuation joins; a moved revision refuses',async()=>{
 const host=new Node(),calls=[];
 renderMaterialObservation(host,paged('# Head\n\npart one ',0,17,'/next'),{request:async path=>{calls.push(path);return paged('part two',17,null);}});
 assert.ok(!host.all().some(node=>node.tag==='h4'));assert.match(host.textContent,/Bounded text page/);
 await button(host,'Read the complete document').onclick();
 assert.deepEqual(calls,['/next']);assert.ok(host.all().some(node=>node.tag==='h4'));assert.match(host.textContent,/part one part two/);
 const other=new Node();
 renderMaterialObservation(other,paged('first',0,5,'/next'),{request:async()=>({...paged('moved',5,null),current_revision:'changed'})});
 await button(other,'Read the complete document').onclick();
 assert.match(other.textContent,/nothing was joined/);assert.ok(!other.textContent.includes('moved'));
});
for(const [consumed,observed,expected] of [
 ['sha256:digest','digest','recorded revision matches observed source'],
 ['earlier','digest','source changed since recorded completion'],
 ['earlier',null,'current source revision unavailable'],
 [null,'digest','consumed revision unavailable'],
])test('Work evidence compares its own consumed basis: '+expected,()=>{
 const host=new Node();renderMaterialObservation(host,{...observation('Read bytes'),current_revision:observed},{
  request:async()=>assert.fail('No additional read'),workEvidence:true,consumedRevision:consumed});
 assert.equal(host.children[0].textContent,'Work evidence: '+expected);
 assert.match(host.textContent,/Workspace material binding/);
 assert.match(host.textContent,/Workspace material consumed: Not linked/);
 assert.match(host.textContent,/observation does not renew this receipt/);
 assert.ok(!host.textContent.includes('engineering CURRENT')&&!host.textContent.includes('scientifically verified'));
});
test('unchanged source follows exact owner controls through completion without writes or invented offsets',async()=>{
 const host=new Node(),url='/projects/material-references?view=workspace-source&consumer=one&id=MAT-one&offset=2&limit=2&page=3&page_count=2',calls=[];
 renderMaterialObservation(host,observation('π🌱',url),{request:async path=>{calls.push(path);return observation('é中');}});
 await button(host,'Read more source').onclick();assert.deepEqual(calls,[url]);assert.match(host.textContent,/é中/);assert.match(host.textContent,/UNBOUND/);assert.equal(button(host,'Read more source'),undefined);
});
test('destroyed observation and foreign/mutating handles cannot update or make a request',async()=>{
 const host=new Node();let release,calls=0;
 const controller=renderMaterialObservation(host,observation('old','/next'),{request:async()=>{calls++;return new Promise(resolve=>{release=()=>resolve(observation('late'));});}});
 const pending=button(host,'Read more source').onclick();controller.destroy();release();await pending;assert.match(host.textContent,/old/);assert.ok(!host.textContent.includes('late'));assert.equal(calls,1);
 assert.throws(()=>materialReadURL({http:{method:'POST',url:'/write'}}),/GET/);
 assert.throws(()=>materialReadURL(handle('https://foreign.test/read')),/outside/);
});

test('destroyed presenter discards late errors and cannot invoke invalidation on its connected slot',async()=>{
 for(const failure of [false,true]){
  const host=new Node();let release,invalidations=0;
  const controller=renderMaterialObservation(host,observation('A','/next'),{request:()=>new Promise((resolve,reject)=>{release=()=>failure?reject(Error('OLD_ERROR')):resolve({...observation('OLD_PAGE'),current_revision:'changed'});}),onInvalidated:()=>invalidations++});
  const pending=button(host,'Read more source').onclick();controller.destroy();renderMaterialObservation(host,{...observation('FRESH_B'),current_revision:'B'},{request:async()=>assert.fail('No request')});release();await pending;
  assert.match(host.textContent,/FRESH_B/);assert.equal(invalidations,0);assert.ok(!host.textContent.includes('OLD_ERROR'));
 }
});
// campaign bounded source reading (2026-10-14): a JSON-record page says which value it is, and pages of
// another record (or another source revision) are never mixed into it; the owner gate admits the pinned route.
test('a JSON-record observation names its value and refuses to mix in a page of another record',async()=>{
 const pin='sha256:'+'a'.repeat(64);
 const record=(content,pointer,next)=>({...observation(content,next),units:'Unicode characters of the selected value\'s JSON serialization',
  owner_result:{content,json_record:{pointer,type:'object',members:6,value_chars:900,value_sha256:'sha256:'+'b'.repeat(64),source_sha256:pin}}});
 const url='/projects/material-references?project=campaign&view=source&id=MAT-one&pointer=%2F1273&offset=120&limit=120&expected_sha256='+pin.slice(7);
 const host=new Node();
 renderMaterialObservation(host,record('{"id": 1273','/1273',url),{request:async()=>record('{"id": 1274','/1274')});
 assert.match(host.textContent,/JSON record \/1273 · object of 6 fields · 900 characters · value sha256:b{64}/);
 await button(host,'Read more source').onclick();
 assert.match(host.textContent,/cannot mix read bases/,'another record is refused, not appended');assert.ok(!host.textContent.includes('1274'));
 const whole=new Node();renderMaterialObservation(whole,record('[','',null),{request:async()=>assert.fail('no read')});
 assert.match(whole.textContent,/JSON record \(whole document\)/);
});
test('the owner gate admits a pinned JSON-record material route and refuses malformed pins and pointers',async()=>{
 const {ownerHumanTarget}=await import('../src/laplace/web/static_shared/writing-owner-read.mjs');
 const base='/projects/material-references?project=campaign&view=source&id=MAT-one';
 const ok=ownerHumanTarget(base+'&pointer=%2F1273%2Fa~1b&expected_sha256='+'a'.repeat(64)+'&offset=120&limit=120');
 assert.equal(ok?.kind,'material-source');assert.equal(ok.pointer,'/1273/a~1b');
 assert.equal(ownerHumanTarget(base+'&pointer=')?.pointer,'','the whole document');
 // repair1 R1: an artifact record's human link is the material preview of that artifact, pinned with its record controls
 const artifact='/projects/material-references?project=campaign&view=preview&target='+encodeURIComponent(JSON.stringify({owner:'artifact',project:'campaign',path:'record.json',scope:'project'}))+'&pointer=%2Fselected&offset=0&limit=6000&expected_sha256=sha256%3A'+'c'.repeat(64);
 const opened=ownerHumanTarget(artifact);assert.equal(opened?.kind,'material-source');assert.equal(opened.pointer,'/selected');assert.equal(opened.target.owner,'artifact');
 // the owner's declared contract (writing-owner-read.mjs: a raw-source pin guards plain excerpts and JSON-pointer reads; the
 // repository owner's expected_sha256 rule says the same): one well-formed pin without a pointer is a lawful whole-source read
 const pinned=ownerHumanTarget(base+'&expected_sha256='+'a'.repeat(64));assert.equal(pinned?.kind,'material-source');assert.equal('pointer' in pinned,false);
 for(const bad of ['&pointer=1273','&pointer=%2F1&expected_sha256=abc','&pointer=%2F1&pointer=%2F2','&expected_sha256=abc','&expected_sha256='+'a'.repeat(64)+'&expected_sha256='+'b'.repeat(64)])
  assert.equal(ownerHumanTarget(base+bad),null,bad);
});

test('failed pinned continuation retains prior page and offers only the issued explicit restart',async()=>{
 const host=new Node(),calls=[],events=[],old={...observation('Retained old page','/next?expected_sha256=old'),restart_read:handle('/current?offset=0')};
 renderMaterialObservation(host,old,{consumedRevision:'digest',workEvidence:true,onObservation:value=>events.push(value.current_revision),onReadError:()=>events.push('read-failed'),request:async url=>{calls.push(url);if(calls.length===1)throw Error('Source revision conflict');return {...observation('New current page'),current_revision:'new-digest'};}});
 await button(host,'Read more source').onclick();assert.deepEqual(calls,['/next?expected_sha256=old']);assert.match(host.textContent,/Retained old page/);assert.match(host.textContent,/Source revision conflict/);
 assert.deepEqual(events,['digest','read-failed']);assert.match(host.textContent,/Earlier observation retained/);
 const restart=button(host,'Restart source observation');assert.ok(restart);assert.equal(host.all().filter(x=>x.tag==='button'&&x.textContent==='Restart source observation').length,1);
 await restart.onclick();assert.deepEqual(calls,['/next?expected_sha256=old','/current?offset=0']);assert.match(host.textContent,/New current page/);assert.match(host.textContent,/source changed since recorded completion/);assert.match(host.textContent,/Recorded evidence consumed: digest/);assert.deepEqual(events,['digest','read-failed','new-digest']);
});
