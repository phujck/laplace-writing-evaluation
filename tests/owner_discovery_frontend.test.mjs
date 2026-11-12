// The System owners app view (workspace-owners.mjs) over replies the REAL owners produced through their HTTP doors
// (tests/test_owner_discovery.py::test_the_owners_view_replies_come_from_the_real_http_door writes them, with their
// status codes, under the guarded run; OWNER_DISCOVERY_REPLIES names that file). No Laplace process is started here.
// The request double behaves as the app's transport: a non-2xx reply throws the owner's error.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {installDOM,findButton} from './helpers/evidence_reader_harness.mjs';
import {mountOwnerDiscovery} from '../src/laplace/web/static_shared/workspace-owners.mjs';
import {renderMaterialObservation} from '../src/laplace/web/static_shared/workspace-material-observation.mjs';

const {task,replies,changed,evidence,source_first,source_pages,material_first,artifact_pages}=JSON.parse(readFileSync(process.env.OWNER_DISCOVERY_REPLIES,'utf8'));
const text=node=>node.textContent;
const tick=()=>new Promise(r=>setTimeout(r,0));

// SYNTHETIC owner replies (explicitly not the real HTTP door): the workspace explanation and exact source journey.
test('synthetic replies: explanation, exact pages, complete inert reading, refused moved join and Back without a request',async()=>{
  installDOM();
  const inputs={reference:{identity:{id:'core.identity'}},basis:'sha256:cut'};
  const page=(content,offset,next,extra={})=>({facet:'source-input',input:{path:'docs/identity.md',sha256:'sha256:pin',bytes:64,roles:['explanation-source']},
    cut:'sha256:cut',content,offset,next_offset:next,pagination:{...(next!=null?{next_read:{http:{url:'/p1'}}}:{previous_read:{http:{url:'/p0'}}}),restart_read:{http:{url:'/x'}}},
    qualification:'Exact declared bytes for orientation.',...extra});
  const table={'/work/discovery?facet=describe':{facet:'describe',purpose:'Start here.',scope:{says:'Owned workspace.'},coverage:{},
      subsystems:[{reference:{identity:{id:'core.identity'}},next:{http:{url:'/d'}},layer:'core',affecting_work:{bound_in_scope:0},summary:'Identity.'}]},
    '/d':{facet:'discover',subsystem:{reference:{identity:{id:'core.identity'}},layer:'core',summary:'Identity owner.',explanation:['docs/identity.md'],
      explanation_read:{http:{url:'/x'}},source_inputs_read:{http:{url:'/i'}}},items:[],up_summary:{says:'No bound Work.',up:{http:{url:'/work/discovery?facet=describe'}}},coverage:{}},
    '/x':{schema_version:'laplace.source-owner-inventory/1',...inputs,items:[{path:'docs/identity.md',sha256:'sha256:pin',bytes:64,roles:['explanation-source'],
      read:{workspace_read:{http:{url:'/p0'}}}}],coverage:{role:'explanation-source',known:1,returned:1,declared_inputs:5,unavailable:[]},pagination:{next_read:null}},
    '/p0':page('# Identity\n\nFirst paragraph.\n\n',0,30),'/p1':page('| A | B |\n|---|---|\n| 1 | 2 |',30,null)};
  const asked=[];const request=async url=>{asked.push(url);const reply=table[url];if(!reply)throw new Error('unexpected '+url);return structuredClone(reply);};
  const host=document.createElement('main');const view=await mountOwnerDiscovery(host,{request});
  await findButton(host,'core.identity').click();
  assert.match(text(host),/Declared explanation: docs\/identity.md/);
  await findButton(host,'Read the explanation').click();
  assert.match(text(host),/1 of 1 explanation-source inputs \(of 5 declared\)/);
  await findButton(host,'docs/identity.md').click();
  await tick();
  // DELIBERATE CHANGE (owners-control-05): the explicit Read of an explanation file now starts the bounded same-cut join
  // itself, once. Exactly the first page and its one issued continuation are read; the earlier pre-join assertions (bounded
  // notice, no table) and the separate Complete click are replaced by the joined state. The two positive outcomes are kept.
  assert.equal(view.visit.value.facet,'source-input');assert.deepEqual(asked.slice(-2),['/p0','/p1'],'one first page and its one issued continuation');assert.equal(asked.filter(url=>url==='/p1').length,1,'the continuation is read once');
  assert.doesNotMatch(text(host),/Bounded text page/);assert.ok(!host.all().some(n=>n.tag==='button'&&n.textContent==='Read the complete document'),'no separate Complete click remains');
  assert.ok(host.all().some(n=>n.tag==='table'));assert.equal(asked.at(-1),'/p1');
  let before=asked.length;view.back();assert.equal(asked.length,before);assert.match(text(host),/explanation-source inputs/);
  table['/p1']=page('moved bytes',30,null,{cut:'sha256:moved'});
  await findButton(host,'docs/identity.md').click();await findButton(host,'Read the complete document').click();await tick();
  assert.match(text(host),/nothing was joined/);assert.ok(!text(host).includes('moved bytes'));assert.match(text(host),/First/);
  before=asked.length;view.back();assert.equal(asked.length,before);
  // the earlier fixture's offsets (next 29, then 18) were not contiguous: kept as an adverse case
  table['/p1']=page('| A | B |',18,null);
  await findButton(host,'docs/identity.md').click();await findButton(host,'Read the complete document').click();await tick();
  assert.match(text(host),/does not continue/);assert.match(text(host),/First/);assert.ok(!host.all().some(n=>n.tag==='table'));
  // inconsistent terminal metadata and changed units refuse without committing the join
  for(const [label,reply,expected] of [['inconsistent terminal',{...page('| A | B |',30,null),next_offset:40},/issued no continuation/],
    ['changed units',{...page('| A | B |',30,null),units:'bytes'},/source changed/]]){
    table['/p1']=reply;view.back();await findButton(host,'docs/identity.md').click();await findButton(host,'Read the complete document').click();await tick();
    assert.match(text(host),expected,label);assert.ok(!host.all().some(n=>n.tag==='table'),label);assert.match(text(host),/First/,label);}
  // owner extents are Unicode scalars: a claimed jump past the actual text and a truncated end refuse
  for(const [label,reply,expected] of [['nonterminal extent jump',page('| A | B |',30,45),/does not end where/],
    ['truncated terminal',{...page('| A | B |',30,null),truncated:true},/issued no continuation/]]){
    table['/p1']=reply;view.back();await findButton(host,'docs/identity.md').click();await findButton(host,'Read the complete document').click();await tick();
    assert.match(text(host),expected,label);assert.ok(!host.all().some(n=>n.tag==='table'),label);assert.match(text(host),/First/,label);}
  // a non-BMP first page: the UTF-16 count (16) is a gap, the code-point count (15) joins
  table['/p0']=page('# Identity π🌱\n\n',0,16);table['/p1']=page('| A | B |\n|---|---|\n| 1 | 2 |',16,null);
  view.back();await findButton(host,'docs/identity.md').click();await findButton(host,'Read the complete document').click();await tick();
  assert.match(text(host),/does not end where/);assert.ok(!host.all().some(n=>n.tag==='table'));assert.match(text(host),/π🌱/);
  table['/p0']=page('# Identity π🌱\n\n',0,15);table['/p1']=page('| A | B |\n|---|---|\n| 1 | 2 |',15,null);
  // DELIBERATE CHANGE (owners-control-05): the explicit explanation Read joins by itself, so no Complete click follows it
  view.back();await findButton(host,'docs/identity.md').click();await tick();
  assert.ok(host.all().some(n=>n.tag==='table'),'scalar extents join');assert.ok(!host.all().some(n=>n.tag==='button'&&n.textContent==='Read the complete document'));assert.match(text(host),/π🌱/);
  // a later page is never assembled as a whole document
  table['/pm']=page('middle',30,36);await view.open('/pm');
  assert.equal(view.visit.value.offset,30);assert.ok(!host.all().some(n=>n.tag==='button'&&n.textContent==='Read the complete document'));assert.match(text(host),/stays paged/);
  view.destroy();
});

// owners-control-05: the ACTUAL System owners caller (mountOwnerDiscovery -> Read the explanation -> the explanation file Read)
// over synthetic owner-shaped replies. This is the owners reader itself, not the shared Material presenter.
test('owners explanation Read: one explicit file Read joins once with its controls above the text and the pane at its beginning; Browse, page links, Back and Reinspect never auto-join; cancel, a late reply and a moved pin stay truthful paged reads',async()=>{
  installDOM();
  const page=(path,content,offset,next,url,extra={})=>({facet:'source-input',input:{path,sha256:'sha256:pin',bytes:64,roles:['explanation-source']},cut:'sha256:cut',units:'Unicode characters',content,offset,next_offset:next,
    pagination:{...(next!=null?{next_read:{http:{url}}}:{}),restart_read:{http:{url:'/x'}}},qualification:'Exact declared bytes.',...extra});
  const inventory=(role,rows)=>({schema_version:'laplace.source-owner-inventory/1',reference:{identity:{id:'core.identity'}},basis:'sha256:cut',
    items:rows.map(([path,url])=>({path,sha256:'sha256:pin',bytes:64,roles:[role],read:url?{workspace_read:{http:{url}}}:{},...(url?{}:{read_unavailable:'no workspace read is issued for this row.'})})),
    coverage:{role,known:rows.length,returned:rows.length,declared_inputs:5,unavailable:[]},pagination:{next_read:null}});
  const table={'/work/discovery?facet=describe':{facet:'describe',purpose:'Start here.',scope:{says:'Owned workspace.'},coverage:{},
      subsystems:[{reference:{identity:{id:'core.identity'}},next:{http:{url:'/d'}},layer:'core',affecting_work:{bound_in_scope:0},summary:'Identity.'}]},
    '/d':{facet:'discover',subsystem:{reference:{identity:{id:'core.identity'}},layer:'core',summary:'Identity owner.',explanation:['docs/identity.md'],
      explanation_read:{http:{url:'/x'}},source_inputs_read:{http:{url:'/i'}}},items:[],up_summary:{says:'No bound Work.',up:{http:{url:'/work/discovery?facet=describe'}}},coverage:{}},
    '/x':inventory('explanation-source',[['docs/identity.md','/p0'],['docs/notes.txt','/t0'],['docs/absent.md',null]]),
    '/i':inventory('source',[['docs/identity.md','/p0']]),
    '/p0':page('docs/identity.md','# Identity\n\nFirst paragraph.\n\n',0,30,'/p1'),'/p1':page('docs/identity.md','| A | B |\n|---|---|\n| 1 | 2 |',30,null),
    '/t0':page('docs/notes.txt','plain first ',0,12,'/t1'),'/t1':page('docs/notes.txt','plain second',12,null)};
  let hold=null;const asked=[];
  const request=async(url,payload)=>{asked.push(url);assert.equal(payload,undefined,'the owners view only reads');if(hold&&url===hold.url)await hold.promise;const reply=table[url];if(!reply)throw new Error('unexpected '+url);return structuredClone(reply);};
  const host=document.createElement('main');const view=await mountOwnerDiscovery(host,{request});
  const has=label=>host.all().some(n=>n.tag==='button'&&n.textContent===label),bar=()=>host.all().find(n=>String(n.className).includes('owner-reading-bar'));
  const before=(a,b)=>{const all=host.all();return all.indexOf(a)>=0&&all.indexOf(a)<all.indexOf(b);};
  const pane=host.all().find(n=>n.className==='owner-discovery');
  await findButton(host,'core.identity').click();await findButton(host,'Read the explanation').click();
  // several inputs: the inventory stays an explicit choice and nothing is read until the person picks a file
  assert.equal(view.visit.value.schema_version,'laplace.source-owner-inventory/1');assert.ok(!asked.includes('/p0'));assert.match(text(host),/Not readable here: no workspace read is issued/);
  pane.scrollTop=400;let mark=asked.length;
  await findButton(host,'docs/identity.md').click();await tick();
  assert.deepEqual(asked.slice(mark),['/p0','/p1'],'exactly the first page and its one issued continuation');
  assert.equal(typeof view.visit.assembled,'string');assert.ok(host.all().some(n=>n.tag==='table'),'the formatted document leads');assert.match(text(host),/Complete · \d+ characters at this cut/);
  assert.ok(has('Reading')&&has('Raw'));assert.ok(!has('Read the complete document')&&!has('Next page')&&!has('Cancel this read'),'the consumed reading controls leave');
  assert.equal(pane.scrollTop,0,'the reading pane is at its beginning');
  assert.ok(before(bar(),host.all().find(n=>n.className==='owner-source-reading')),'the reading bar is above the text');assert.ok(bar().all().includes(findButton(host,'Current inventory')));
  // Back returns the retained inventory without a request; a page link and Reinspect read their own page and never auto-join
  mark=asked.length;assert.equal(view.back(),true);assert.equal(asked.length,mark);assert.equal(view.visit.value.schema_version,'laplace.source-owner-inventory/1');
  await view.open('/p0');assert.deepEqual(asked.slice(mark),['/p0'],'a page link reads its one page');assert.match(text(bar()),/Bounded text page/);
  assert.ok(bar().all().includes(findButton(host,'Read the complete document'))&&bar().all().includes(findButton(host,'Next page')),'the complete action and paging sit above the bounded text');
  assert.ok(before(bar(),host.all().find(n=>n.tag==='pre'&&n.className==='owner-source-bytes')));
  mark=asked.length;await view.reinspect();assert.deepEqual(asked.slice(mark),['/p0'],'Reinspect rereads its own handle only');assert.ok(!host.all().some(n=>n.tag==='table'));
  mark=asked.length;findButton(host,'Read the complete document').focus?.();assert.equal(asked.length,mark,'focus never fetches');
  // Browse declared source: the same file opened from the source inventory stays an exact paged read
  await view.open('/i');mark=asked.length;await findButton(host,'docs/identity.md').click();await tick();
  assert.deepEqual(asked.slice(mark),['/p0'],'Browse does not auto-join');assert.ok(has('Read the complete document'));assert.ok(!host.all().some(n=>n.tag==='table'));
  // a non-Markdown explanation input stays paged: no complete action, paging above the text
  await view.open('/x');mark=asked.length;await findButton(host,'docs/notes.txt').click();await tick();
  assert.deepEqual(asked.slice(mark),['/t0']);assert.ok(!has('Read the complete document'));assert.ok(bar().all().includes(findButton(host,'Next page')));assert.doesNotMatch(text(host),/Bounded text page/);
  // a delayed join: Cancel is offered above the text, the late reply joins nothing and the page is kept
  await view.open('/x');let release;hold={url:'/p1',promise:new Promise(resolve=>{release=resolve;})};mark=asked.length;
  const reading=findButton(host,'docs/identity.md').click();for(let n=0;n<20&&!has('Cancel this read');n++)await tick();
  assert.ok(bar().all().includes(findButton(host,'Cancel this read')),'Cancel sits in the reading bar');assert.ok(!has('Read the complete document'));
  await findButton(host,'Cancel this read').click();
  assert.match(text(host),/Complete reading cancelled\. The page you were reading is kept\./);assert.ok(has('Read the complete document'));
  release();hold=null;await reading;await tick();
  assert.deepEqual(asked.slice(mark),['/p0','/p1']);assert.equal(view.visit.assembled,undefined,'the late reply joins nothing');assert.ok(!host.all().some(n=>n.tag==='table'));assert.match(text(host),/First paragraph/);
  // a moved pin refuses the automatic join with a visible reason and the owner restart above the text; the page stays exact
  table['/p1']=page('docs/identity.md','moved bytes',30,null,undefined,{input:{path:'docs/identity.md',sha256:'sha256:other',bytes:64,roles:['explanation-source']}});
  await view.open('/x');await findButton(host,'docs/identity.md').click();await tick();
  const refusal=bar().all().find(n=>n.dataset?.refusal!==undefined);
  assert.ok(refusal,'the refusal is in the reading bar');assert.match(text(refusal),/source changed between pages, so nothing was joined/i);assert.match(text(refusal),/The page you were reading is kept\./);
  assert.ok(bar().all().includes(findButton(host,'Current inventory')),'the owner restart is beside the refusal');assert.ok(has('Read the complete document'));assert.ok(!text(host).includes('moved bytes'));assert.match(text(host),/First paragraph/);
  view.destroy();
});

// async-owner-cases-06: the ACTUAL System owners reader across a DELAYED read. A repaint replaces the view's nodes, so the focus
// the person moved to during the delay is resolved again on the same qualified control; nothing else takes focus.
test('owners delayed explanation read keeps the focus the person moved to: the same connected Back or Current inventory control is focused again after a delayed success and after a delayed refusal; outside focus and a newer visit are untouched; the heading takes focus only while the consumed read still owns it; focus never fetches and Cancel ends only its own read',async()=>{
  const env=installDOM();
  const page=(content,offset,next,extra={})=>({facet:'source-input',input:{path:'docs/identity.md',sha256:'sha256:pin',bytes:64,roles:['explanation-source']},cut:'sha256:cut',units:'Unicode characters',content,offset,next_offset:next,
    pagination:{...(next!=null?{next_read:{http:{url:'/p1'}}}:{}),restart_read:{http:{url:'/x'}}},qualification:'Exact declared bytes.',...extra});
  const good=page('| A | B |\n|---|---|\n| 1 | 2 |',30,null),moved=page('moved bytes',30,null,{cut:'sha256:moved'});
  const table={'/work/discovery?facet=describe':{facet:'describe',purpose:'Start here.',scope:{says:'Owned workspace.'},coverage:{},
      subsystems:[{reference:{identity:{id:'core.identity'}},next:{http:{url:'/d'}},layer:'core',affecting_work:{bound_in_scope:0},summary:'Identity.'}]},
    '/d':{facet:'discover',subsystem:{reference:{identity:{id:'core.identity'}},layer:'core',summary:'Identity owner.',explanation:['docs/identity.md'],
      explanation_read:{http:{url:'/x'}},source_inputs_read:{http:{url:'/i'}}},items:[],up_summary:{says:'No bound Work.',up:{http:{url:'/work/discovery?facet=describe'}}},coverage:{}},
    '/x':{schema_version:'laplace.source-owner-inventory/1',reference:{identity:{id:'core.identity'}},basis:'sha256:cut',items:[{path:'docs/identity.md',sha256:'sha256:pin',bytes:64,roles:['explanation-source'],read:{workspace_read:{http:{url:'/p0'}}}}],
      coverage:{role:'explanation-source',known:1,returned:1,declared_inputs:5,unavailable:[]},pagination:{next_read:null}},
    '/p0':page('# Identity\n\nFirst paragraph.\n\n',0,30),'/p1':good};
  let hold=null;const asked=[],signals=[];
  const request=async(url,payload,options)=>{asked.push(url);assert.equal(payload,undefined,'the owners view only reads');if(url==='/p1')signals.push(options?.signal||null);if(hold&&url===hold.url)await hold.promise;const reply=table[url];if(!reply)throw new Error('unexpected '+url);return structuredClone(reply);};
  const host=document.createElement('main');const view=await mountOwnerDiscovery(host,{request});
  const has=label=>host.all().some(n=>n.tag==='button'&&n.textContent===label),pane=host.all().find(n=>n.className==='owner-discovery');
  // `shown` is membership of the CURRENT paint: a node an earlier paint created is not in it
  const shown=node=>pane.all().includes(node),focused=()=>document.activeElement,inventory=()=>view.visit.value.schema_version==='laplace.source-owner-inventory/1';
  await findButton(host,'core.identity').click();await findButton(host,'Read the explanation').click();assert.ok(inventory());
  // one delayed explicit Read from the inventory on screen; its continuation is held until it is released
  const delayed=async()=>{assert.ok(inventory(),'each delayed read starts from the inventory');let release;hold={url:'/p1',promise:new Promise(resolve=>{release=resolve;})};
    const reading=findButton(host,'docs/identity.md').click();for(let n=0;n<20&&!has('Cancel this read');n++)await tick();
    assert.ok(has('Cancel this read'));assert.equal(focused(),findButton(host,'Cancel this read'),'while the read owns focus it is on its own Cancel');
    return {release:()=>{release();hold=null;},settle:async()=>{release();hold=null;await reading;await tick();}};};
  // DELAYED SUCCESS with focus moved to Current inventory: the same qualified control has focus in the repainted view
  let run=await delayed(),mark=asked.length;const chosen=findButton(host,'Current inventory');chosen.focus();assert.equal(asked.length,mark,'focus never fetches');
  pane.scrollTop=120;await run.settle();
  assert.equal(typeof view.visit.assembled,'string');assert.ok(host.all().some(n=>n.tag==='table'),'the formatted document is shown');assert.ok(has('Reading')&&has('Raw'),'Reading and exact Raw stay');
  assert.ok(shown(focused()),'focus is on a control of the painted view, never on a removed node');assert.equal(focused().textContent,'Current inventory');assert.equal(focused().dataset.url,'/x');assert.notEqual(focused(),chosen,'the node was replaced and the same control resolved again');
  assert.equal(pane.scrollTop,120,'the reading position is not taken from a person who moved on');assert.equal(asked.length,mark,'resolving focus never fetches');
  // DELAYED SUCCESS with focus moved to Back: Back keeps focus and still returns the retained inventory without a request
  assert.equal(view.back(),true);run=await delayed();findButton(host,/^Back to /).focus();await run.settle();
  assert.equal(typeof view.visit.assembled,'string');assert.ok(shown(focused()));assert.notEqual(focused().dataset.back,undefined,'Back keeps focus');assert.equal(focused().textContent,'Back to declared source');
  mark=asked.length;focused().onclick();assert.ok(inventory(),'Back returns the retained inventory');assert.equal(asked.length,mark,'Back makes no request');
  // DELAYED SUCCESS while the consumed read still owns focus: the heading takes it and the view's own top is brought into reach
  run=await delayed();pane.scrollTop=400;await run.settle();
  assert.equal(focused().tag,'h3');assert.ok(shown(focused()));assert.equal(focused().focusOptions?.preventScroll,true,'the heading takes focus without scrolling past Back');
  assert.equal(pane.scrollTop,0);assert.ok(String(pane.children[0].className).includes('owner-nav')&&pane.children[0].revealed>0,'Back and the read time are brought into reach above the heading');
  // DELAYED SUCCESS with focus OUTSIDE this view: neither focus nor the reading position is taken
  assert.equal(view.back(),true);run=await delayed();env.editor.focus();pane.scrollTop=250;await run.settle();
  assert.equal(typeof view.visit.assembled,'string');assert.equal(focused(),env.editor,'outside focus is never stolen');assert.equal(pane.scrollTop,250);
  // DELAYED REFUSAL (the source moved between pages): the same holds, and the refusal sits beside the controls
  table['/p1']=moved;
  for(const [label,pick,check] of [
    ['Current inventory',()=>findButton(host,'Current inventory'),node=>node.textContent==='Current inventory'&&node.dataset.url==='/x'],
    ['Back',()=>findButton(host,/^Back to /),node=>node.dataset.back!==undefined]]){
    assert.equal(view.back(),true,label);run=await delayed();const before=pick();before.focus();mark=asked.length;await run.settle();
    assert.equal(view.visit.assembled,undefined,label);assert.match(text(host.all().find(n=>n.dataset?.refusal!==undefined)),/source changed between pages, so nothing was joined/i,label);assert.match(text(host),/First paragraph/,label);
    assert.ok(shown(focused()),label+': focus is on a control of the repainted view');assert.ok(check(focused()),label+' keeps focus after the refusal');assert.notEqual(focused(),before,label);
    assert.equal(asked.length,mark,label+': no fetch');assert.ok(has('Read the complete document'),label);}
  assert.equal(view.back(),true);run=await delayed();await run.settle();
  assert.equal(focused().dataset.readingControl,'complete','a refusal while the read still owns focus returns it to the complete action');assert.ok(shown(focused()));
  assert.equal(view.back(),true);run=await delayed();env.editor.focus();await run.settle();assert.equal(focused(),env.editor,'a refusal never takes outside focus');
  // A GENUINE NEWER VISIT during the delay: the late reply paints nothing, fetches nothing and moves no focus
  table['/p1']=good;assert.equal(view.back(),true);run=await delayed();
  await findButton(host,'Current inventory').click();assert.ok(inventory(),'the person opened the current inventory');
  const later=findButton(host,'docs/identity.md');later.focus();mark=asked.length;await run.settle();
  assert.ok(inventory());assert.equal(focused(),later,'the newer visit keeps its own focus');assert.equal(asked.length,mark,'the late reply fetches nothing');assert.ok(!host.all().some(n=>n.tag==='table'));
  assert.equal(view.back(),true);assert.equal(view.visit.value.facet,'source-input');assert.equal(view.visit.assembled,undefined,'the late reply joined nothing');
  assert.ok(has('Read the complete document')&&!has('Cancel this read'),'the retained page is an ordinary paged read again');
  // SCOPED CANCELLATION: Cancel ends only its own read; a later read of the same page completes and the cancelled late reply changes nothing
  assert.equal(view.back(),true);run=await delayed();const first=signals.length-1;await findButton(host,'Cancel this read').click();
  assert.equal(focused().dataset.readingControl,'complete','Cancel returns focus to the complete action');assert.equal(signals[first]?.aborted,true,'Cancel aborts its own GET');
  hold=null;await findButton(host,'Read the complete document').click();await tick();
  assert.equal(typeof view.visit.assembled,'string','the later read completes');assert.equal(signals.at(-1)?.aborted,false,'the later read is not cancelled by the earlier Cancel');assert.equal(focused().tag,'h3');
  const joined=view.visit.assembled,kept=focused();run.release();await tick();await tick();
  assert.equal(view.visit.assembled,joined);assert.equal(focused(),kept,'the cancelled late reply changes nothing');assert.ok(host.all().some(n=>n.tag==='table'));
  view.destroy();env.restore();
});

test('near-cap hostile and dense Markdown read through the owners view within one budget; Reading and Raw keep the same eligibility',async()=>{
  installDOM();
  const doc=(path,content)=>({facet:'source-input',input:{path,sha256:'sha256:pin',bytes:content.length,roles:['explanation-source']},cut:'sha256:cut',
    content,offset:0,next_offset:null,pagination:{restart_read:{http:{url:'/work/discovery?facet=describe'}}},qualification:'Exact declared bytes.'});
  const brackets='['.repeat(262000),dense='- a\n'.repeat(60000);
  const table={'/work/discovery?facet=describe':{facet:'describe',purpose:'Start here.',scope:{says:'Owned workspace.'},coverage:{},subsystems:[]},
    '/brackets':doc('docs/brackets.md',brackets),'/dense':doc('docs/dense.md',dense)};
  const request=async url=>{const reply=table[url];if(!reply)throw new Error('unexpected '+url);return structuredClone(reply);};
  const host=document.createElement('main');const view=await mountOwnerDiscovery(host,{request});
  await view.open('/brackets');assert.equal(view.visit.value.facet,'source-input');assert.doesNotMatch(text(host),/could not be shown/);
  assert.ok(host.all().some(n=>n.className==='markdown-reading'));
  await findButton(host,'Raw').click();await findButton(host,'Reading').click();assert.ok(host.all().some(n=>n.className==='markdown-reading'));
  await view.open('/dense');assert.match(text(host),/too large or too dense/);assert.ok(!host.all().some(n=>n.tag==='li'));
  assert.equal(host.all().find(n=>n.tag==='pre'&&n.className==='material-source-reading').textContent,dense);
  await findButton(host,'Reading').click();assert.match(text(host),/too large or too dense/);assert.ok(!host.all().some(n=>n.tag==='li'));
  assert.equal(view.back(),true);assert.equal(view.visit.value.input.path,'docs/brackets.md');
  // a single page whose terminal fields contradict it stays exact text; a valid empty complete page reads whole
  table['/single']={...doc('docs/single.md','# Only'),next_offset:12};table['/empty']=doc('docs/empty.md','');
  await view.open('/single');assert.match(text(host),/issued no continuation/);assert.ok(!host.all().some(n=>n.className==='markdown-reading'));
  assert.ok(!host.all().some(n=>n.tag==='button'&&n.textContent==='Read the complete document'));
  assert.equal(host.all().find(n=>n.tag==='pre'&&n.className==='owner-source-bytes').textContent,'# Only');
  await view.open('/empty');assert.ok(host.all().some(n=>n.className==='markdown-reading'));assert.doesNotMatch(text(host),/issued no continuation/);
  assert.equal(view.back(),true);assert.equal(view.visit.value.input.path,'docs/single.md');
  view.destroy();
});

// SYNTHETIC owner replies: hostile nested Markdown in the owners view, and an unexpected paint failure of a malformed reply.
test('hostile nested Markdown reads bounded in the owners view, and a paint failure keeps the last good visit and Back',async()=>{
  installDOM();
  const hostile='>'.repeat(20000)+' deepest words';
  const table={'/work/discovery?facet=describe':{facet:'describe',purpose:'Start here.',scope:{says:'Owned workspace.'},coverage:{},
      subsystems:[{reference:{identity:{id:'core.broken'}},next:{http:{url:'/broken'}},layer:'core',affecting_work:{bound_in_scope:0},summary:'Malformed reply.'},
        {reference:{identity:{id:'core.deep'}},next:{http:{url:'/deep'}},layer:'core',affecting_work:{bound_in_scope:0},summary:'Deep source.'}]},
    '/broken':{facet:'discover',items:[],coverage:{}},
    '/deep':{facet:'source-input',input:{path:'docs/deep.md',sha256:'sha256:pin',bytes:hostile.length,roles:['explanation-source']},cut:'sha256:cut',
      content:hostile,offset:0,next_offset:null,pagination:{restart_read:{http:{url:'/work/discovery?facet=describe'}}},qualification:'Exact declared bytes.'}};
  const request=async url=>{const reply=table[url];if(!reply)throw new Error('unexpected '+url);return structuredClone(reply);};
  const host=document.createElement('main');const view=await mountOwnerDiscovery(host,{request});
  await findButton(host,'core.broken').click();await tick();
  assert.equal(view.visit.value.facet,'describe');assert.equal(view.back(),false);
  assert.match(text(host),/could not be shown/);assert.match(text(host),/The previous view is kept/);assert.match(text(host),/All subsystems/);
  await findButton(host,'core.deep').click();await tick();
  assert.equal(view.visit.value.facet,'source-input');assert.match(text(host),/deepest words/);
  assert.match(text(host),/Quote nesting deeper than 8 levels/);
  assert.equal(view.back(),true);assert.equal(view.visit.value.facet,'describe');assert.match(text(host),/All subsystems/);
  view.destroy();
});

// GENUINE owner pages from the exporter: the inventory owner's Source-input pages (Unicode scalars, CRLF normalised) and the
// Artifact owner's pages (UTF-8 bytes, size_bytes, complete). Both existing consumers join them; owner-claim variants refuse.
test('genuine owner pages: both consumers join exact scalar and UTF-8 spans; jumps, remaining suffixes and changed units refuse',async()=>{
  installDOM();
  // the export is sort_keys JSON: order pages by the owner's own offsets, never by key text
  const urls=Object.keys(source_pages).sort((a,b)=>source_pages[a].offset-source_pages[b].offset),last=urls.at(-1),head=source_pages[source_first];
  assert.ok(urls.length>=2&&urls[0]===source_first&&head.offset===0);
  let override={};
  const table={'/work/discovery?facet=describe':{facet:'describe',purpose:'Start here.',scope:{says:'Owned workspace.'},coverage:{},subsystems:[]}};
  const request=async url=>{const reply=override[url]??source_pages[url]??table[url];if(!reply)throw new Error('unexpected '+url);return structuredClone(reply);};
  const host=document.createElement('main');const view=await mountOwnerDiscovery(host,{request});
  await view.open(source_first);await findButton(host,'Read the complete document').click();await tick();
  assert.ok(host.all().some(n=>n.tag==='table'),'genuine scalar pages join');assert.match(text(host),/π\u{1F331}/u);
  for(const [label,url,reply,expected] of [['first-page extent jump',source_first,{...head,next_offset:head.next_offset+1},/does not end where/],
    ['terminal remaining suffix',last,{...source_pages[last],next_offset:source_pages[last].offset+5},/issued no continuation/],
    ['truncated terminal',last,{...source_pages[last],truncated:true},/issued no continuation/],
    ['changed units',urls[1],{...source_pages[urls[1]],units:'UTF-8 bytes'},/source changed/]]){
    override={[url]:reply};await view.open(source_first);await findButton(host,'Read the complete document').click();await tick();
    assert.match(text(host),expected,label);assert.ok(!host.all().some(n=>n.tag==='table'),label);
    assert.equal(host.all().find(n=>n.tag==='pre'&&n.className==='owner-source-bytes').textContent,(override[source_first]||head).content,label);
    assert.equal(view.back(),true,label);}
  override={};view.destroy();
  // the Material consumer over the library Material owner's own Artifact preview replies, keyed by its issued GET URLs
  const local=url=>{const u=new URL(url,'http://local/');return u.pathname+u.search;};
  const lookup=Object.fromEntries(Object.entries(artifact_pages).map(([url,reply])=>[url===material_first?url:local(url),reply]));
  const result=reply=>reply.owner_result||reply;
  const order=Object.keys(lookup).sort((a,b)=>result(lookup[a]).offset-result(lookup[b]).offset);
  assert.ok(order.length>=2&&order[0]===material_first&&result(lookup[material_first]).offset===0);
  const settle=async()=>{for(let k=0;k<8;k++)await tick();};
  const material=async variants=>{const place=document.createElement('div');place.isConnected=true;
    renderMaterialObservation(place,structuredClone(variants[material_first]||lookup[material_first]),{request:async url=>{const reply=variants[url]||lookup[url];if(!reply)throw new Error('unexpected '+url);return structuredClone(reply);}});
    await findButton(place,'Read the complete document').click();await settle();return place;};
  const joined=await material({});
  assert.ok(joined.all().some(n=>n.tag==='table'),'genuine library Material Artifact pages join unchanged');assert.match(text(joined),/π\u{1F331}/u);
  // negative variants only: one owner field changed on an otherwise exact reply
  const variant=(url,change)=>{const reply=structuredClone(lookup[url]);change(result(reply));return {[url]:reply};};
  const end=order.at(-1);
  for(const [label,variants,expected] of [['byte extent jump',variant(material_first,r=>{r.next_offset+=1;}),/does not end where/],
    ['changed total',variant(end,r=>{r.size_bytes+=1;}),/Source changed/],
    ['incomplete terminal',variant(end,r=>{r.complete=false;}),/issued no continuation/],
    ['terminal remaining suffix',variant(end,r=>{r.next_offset=r.offset+3;}),/issued no continuation/]]){
    const place=await material(variants);assert.match(text(place),expected,label);assert.ok(!place.all().some(n=>n.tag==='table'),label);}
});

// REAL owner DTO (copied verbatim in its used fields from the isolated S019 owner call Root recorded as
// development/p6-connected-frontend-implementation-20261104/source-01/actual-fixture-discovery-next.json,
// sha256 3d0a78d4dde0b4c40f5c0eb703bf4d15d6e2015c4b7b841478c3b8f211dfd79b): Next readiness READY with task/task_status needing
// forms, planning carrying an exact owner POST payload and review_setup a GET. The view shows each by kind and promotes none.
const REAL_INSPECT={facet:'inspect',grade:'execution',scope:{kind:'owned-workspace',door:'http',says:'The local owned workspace: every namespace this root holds is readable here.'},
  reference:{schema_version:'laplace.reference/1',owner:'domain.work',kind:'work',identity:{namespace:'integration-clean',id:'WORK-public-acceptance-fixture-core-identity-20261104'},
    version:{work_revision:'sha256:7809512cd9aae06c43bcbb939e2d02774a4c909f200f7684fb8ffaecb755871d'},
    legacy:{qualified_id:'integration-clean::WORK-public-acceptance-fixture-core-identity-20261104',read:{operation:'project',payload:{namespace:'integration-clean',view:'detail',id:'WORK-public-acceptance-fixture-core-identity-20261104'},http:{method:'GET',url:'/work/state?project=integration-clean&view=detail&id=WORK-public-acceptance-fixture-core-identity-20261104'}}}},
  version:{requested:null,status:'UNVERSIONED',says:'No version was requested; the current object is read.'},
  title:'Test-only: core.identity reading and Related Work',purpose:'Exercise the public isolated core.identity explanation, Related Work, supporting evidence and Back journey. Withdraw this test-only fixture after the walk. This record claims no production or receipt.',
  standing:{status:'ready',recorded_status:'open',readiness:{status:'READY',blocked_by:[],reason:'task is not complete'},current_acceptance:{status:'NOT_REQUIRED',review_required:false}},blockers:[],
  activity:{state:null,qualification:'No in-app or attested external execution is observed for this Work.',observations:[]},
  next:{readiness:'READY',actions:[
    {name:'task',permitted:true,http:{method:'POST',url:'/work/task'},requires:'Author changed fields using this exact specification guard; omitted fields retain their meaning.'},
    {name:'task_status',permitted:true,http:{method:'POST',url:'/work/transition'},requires:'Choose explicit standing. Done requires current prerequisites and completion evidence; held work must be explicitly resumed.'},
    {name:'planning',permitted:true,http:{method:'POST',url:'/work/task',payload:{project:'integration-clean',action:'planning',id:'WORK-public-acceptance-fixture-core-identity-20261104',request_id:'PLAN-acb2fb365afd41d7ae32fa965617c53a',expected_work_revision:'sha256:7809512cd9aae06c43bcbb939e2d02774a4c909f200f7684fb8ffaecb755871d',expected_planning_revision:'sha256:6538b5c5a178f231b214d89bafc94e36631b44c4222a0be6e157d1be2ef0d307',planning:{priority:0,order:0,deferred:false,reason:''}}},requires:null,intent_projection:{algorithm:'sha256-canonical-json-utf8',excluded_fields:['request_id']}},
    {name:'review_setup',permitted:true,http:{method:'GET',url:'/work/delivery?project=integration-clean&request=%7B%22action%22%3A%22review-setup%22%2C%22work_id%22%3A%22WORK-public-acceptance-fixture-core-identity-20261104%22%7D'},requires:null}],
    says:"Actions run through the Work owner's own admitted doors with their exact guards; this read admits none."},
  evidence:{items:[{owner:'completion-evidence',path:'synthetics papers/integration-clean/acceptance-fixtures/core-identity-related-work.md',consumed_revision:null,http:{method:'GET',url:'/research/artifact?project=integration-clean&scope=project&path=acceptance-fixtures%2Fcore-identity-related-work.md'},available:true}],total:1,truncated:false,continuation:null,says:'Each item is the Work owner\'s own evidence read.'},
  binding:{binding_revision:'sha256:ba679366b3f5f289a2c634d065b444e1611641ac8dfa6f0952d965ab67cc1a7b',history:1,consumed_work_revision:'sha256:7809512cd9aae06c43bcbb939e2d02774a4c909f200f7684fb8ffaecb755871d'},
  up:[{relation:'targets',reference:{schema_version:'laplace.reference/1',owner:'core.identity',kind:'subsystem',identity:{id:'core.identity'}},next:{http:{method:'GET',url:'/work/discovery?facet=discover&subsystem=core.identity'}}}],lateral:[],
  read_cut:{work:{revision:'sha256:6ec2e62c31f0c90995d86da77b6485b7d07b23415334635e9876efbba24d8c20'}},coverage:{children:0,evidence_truncated:false,withheld:null,unbound:null},
  // the recorded DTO carries the project-qualified legacy read at top level as well as under reference; the editor and Open in project consume it
  legacy:{qualified_id:'integration-clean::WORK-public-acceptance-fixture-core-identity-20261104',read:{operation:'project',payload:{namespace:'integration-clean',view:'detail',id:'WORK-public-acceptance-fixture-core-identity-20261104'},http:{method:'GET',url:'/work/state?project=integration-clean&view=detail&id=WORK-public-acceptance-fixture-core-identity-20261104'}}}};
test('real owner Next: READY is view-level readiness, actions show by kind (form / owner template / inspect-only), nothing is promoted, Back names its target',async()=>{
  installDOM();
  const table={'/work/discovery?facet=describe':{facet:'describe',purpose:'Start here.',scope:{says:'Owned workspace.'},coverage:{},subsystems:[]},'/real':REAL_INSPECT,'/real-no-next':{...REAL_INSPECT,next:undefined},
    [REAL_INSPECT.next.actions[3].http.url]:{action:'review-setup',work_id:'WORK-public-acceptance-fixture-core-identity-20261104',says:'synthetic body behind the real owner GET handle'}};
  const asked=[];const request=async(url,payload)=>{asked.push({url,payload});const reply=table[url];if(!reply)throw new Error('unexpected '+url);return structuredClone(reply);};
  let opened=null;const host=document.createElement('main');const view=await mountOwnerDiscovery(host,{request,onWork:target=>{opened=target;}});
  await view.open('/real');assert.equal(view.visit.value.facet,'inspect');
  const dd=term=>{const nodes=host.all().filter(n=>n.tag==='dt'&&n.textContent===term);assert.equal(nodes.length,1,term);const parent=nodes[0].parent||nodes[0].parentNode||nodes[0].parentElement;const kids=[...(parent.children||parent.childNodes||[])];return kids[kids.indexOf(nodes[0])+1].textContent;};
  // the owner's readiness word is shown as its own view-level fact, never as a recommended action
  assert.equal(dd('Owner readiness'),'READY','the readiness word is a fact under About this read');
  assert.match(dd('task'),/^Needs a form in the project: Author changed fields/);assert.match(dd('task_status'),/^Needs a form in the project: Choose explicit standing/);
  assert.match(dd('planning'),/^Owner-issued template; not run from here · POST \/work\/task$/);
  assert.match(dd('review_setup'),/^Inspect-only read \(GET\) · GET \/work\/delivery$/);
  assert.equal(dd('Permitted at this read'),'task, task_status, planning, review_setup');
  assert.equal(dd('Activity'),'No in-app or attested external execution is observed for this Work.');assert.doesNotMatch(text(host),/Stop applies/);
  // Next by kind, usable: task opens the editor (one primary), the other POSTs open the project page, the GET opens its owner read here
  const kinds=host.all().filter(n=>n.dataset?.nextKind).map(n=>[n.textContent,n.dataset.nextKind,n.className]);
  assert.deepEqual(kinds,[['Edit title and purpose','form','act primary'],['task status · open the project form','form','act'],['planning · owner template · open in project','template','act'],['review setup · inspect','inspect','act']]);
  assert.ok(!host.all().some(n=>n.tag==='button'&&/continue/i.test(n.textContent)),'no Continue is issued or promoted');
  await findButton(host,'planning · owner template · open in project').click();assert.equal(opened?.id,'WORK-public-acceptance-fixture-core-identity-20261104');
  await findButton(host,'review setup · inspect').click();assert.equal(view.visit.value.action,'review-setup');assert.equal(view.back(),true);
  assert.match(dd('Work revision'),/^sha256:7809512c/);assert.match(dd('Read cut'),/^sha256:6ec2e62c/);
  assert.ok(host.all().some(n=>n.tag==='button'&&n.textContent==='Open evidence'));
  // Back names the retained visit it returns to
  await findButton(host,'Back to System entry').onclick();assert.equal(view.visit.value.facet,'describe');
  // a detail without next (the recorded owner detail DTO carries next:null) is unknown at this read, not READY
  await view.open('/real-no-next');assert.match(text(host),/Unknown at this read: the owner issued no next\./);assert.doesNotMatch(text(host),/Owner readiness/);
  assert.ok(asked.every(entry=>entry.payload===undefined),'every request was a read');
  view.destroy();
});

test('the owners view follows owner handles and the selected evidence read, and marks retained results',async()=>{
  installDOM();
  const asked=[];let opened=null,table=replies,hold=null;
  const request=async(url,payload)=>{asked.push({url,payload});if(payload!==undefined)throw new Error('the owners view never writes');
    if(hold&&url===hold.url)await hold.promise;
    const reply=table[url]||replies[url];if(!reply)throw new Error('the view asked for a URL no owner returned: '+url);
    if(reply.code>=400){const error=Error(reply.value.error||('status '+reply.code));error.result=reply.value;throw error;}
    return structuredClone(reply.value);};
  const host=document.createElement('main');
  let clock=Date.parse('2026-10-21T12:00:00Z');const now=()=>new Date(clock);
  const view=await mountOwnerDiscovery(host,{request,onWork:target=>{opened=target;},now});
  assert.equal(view.visit.value.facet,'describe');assert.match(text(host),/Read from the owner at 2026-10-21 12:00:00 UTC/);
  const form=host.all().find(n=>n.tag==='form');form.children.find(n=>n.tag==='input').value=task;
  await form.onsubmit({preventDefault(){}});await tick();
  assert.match(text(host),/Nothing was selected for you/);
  await findButton(host,'adapter.desktop').click();
  await findButton(host,'Harden the shared interaction and configuration design').click();
  assert.equal(view.visit.value.facet,'inspect');
  assert.match(text(host),/External running, observed/);assert.match(text(host),/current at this read/);assert.match(text(host),/Permitted at this read/);
  assert.match(text(host),/All 7 evidence reads in the project Work/);
  await findButton(host,'Reconcile the Laplace engine, its interfaces and living guide').click();
  await findButton(host,'Organise the owned system into one coherent implementation tree').click();
  // the expired observation stays qualified as the owner says; each evidence action is that item's own owner read
  assert.match(text(host),/UNKNOWN now/);assert.match(text(host),/not current at this read/);
  const reads=host.all().filter(n=>n.tag==='button'&&n.textContent==='Open evidence').map(n=>n.dataset.url);
  assert.deepEqual(reads.map(url=>url.split('?')[0]),['/research/artifact','/projects/material-references']);
  assert.match(reads[0],/expected_sha256=[0-9a-f]{64}/);
  // the selected evidence: its own owner read, then the owner's refusal once the pinned bytes changed
  const read=findButton(host,'Open evidence');assert.equal(read.dataset.url,evidence);
  await read.click();assert.match(text(host),/R1-R5 physical programme: done/);
  table=changed;await findButton(host,'Open evidence').click();
  assert.match(text(host),/The evidence owner refused this read: /);table=replies;
  // a late evidence response after navigating away never paints
  let release;hold={url:evidence,promise:new Promise(r=>{release=r;})};
  const late=findButton(host,'Open evidence').click();view.back();release();await late;hold=null;
  assert.doesNotMatch(text(host),/R1-R5 physical programme/);
  // Back repainted the retained campaign result without a request, visibly retained; Reinspect rereads it
  clock+=60000;const before=asked.length;
  assert.equal(host.all().find(n=>n.dataset?.freshness)?.dataset.freshness,'retained');
  assert.match(text(host),/Retained result read at 2026-10-21 12:00:00 UTC; not reread/);
  await findButton(host,'Reinspect').click();assert.equal(asked.length,before+1);
  assert.equal(host.all().find(n=>n.dataset?.freshness)?.dataset.freshness,'fresh');assert.match(text(host),/Read from the owner at 2026-10-21 12:01:00 UTC/);
  view.back();assert.match(text(host),/Retained result read at/);assert.match(text(host),/Harden the shared interaction/);
  await findButton(host,'Open in project').click();
  assert.deepEqual({project:opened.project,id:opened.id},{project:'writing-system-architecture',id:'WORK-frontend-interaction-hardening-20261021'});
  assert.equal(opened.read.http.url,'/work/state?project=writing-system-architecture&view=detail&id=WORK-frontend-interaction-hardening-20261021');
  assert.ok(asked.every(entry=>entry.payload===undefined),'every request was a read');
  view.destroy();
});
