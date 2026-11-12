import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,stat} from 'node:fs/promises';
import {installDOM,findButton} from './helpers/evidence_reader_harness.mjs';
import {openFeedbackComment,openFeedbackResponses} from '../src/laplace/web/static_shared/feedback-route.mjs';
const vector=process.env.FEEDBACK_ORIGIN_VECTOR?JSON.parse(await readFile(process.env.FEEDBACK_ORIGIN_VECTOR,'utf8')):null;
// The owner test's retained resolved-successor-actual vector (a file, or the evidence directory holding it).
const routeVectorFile=await (async()=>{const home=process.env.FEEDBACK_ROUTE_VECTOR;if(!home)return null;const found=await stat(home).catch(()=>null);return found?.isDirectory()?home+'/resolved-successor-actual.json':found?home:null;})();
const routeVector=routeVectorFile?JSON.parse(await readFile(routeVectorFile,'utf8')):null;
// The same-scratch producer's CURRENT owner request comparison/association/settlement DTOs (test_feedback_route._request_recovery_export).
const recoveryVector=routeVector?.request_recovery||null;
const storage=()=>{const map=new Map();return {getItem:key=>map.get(key)||null,setItem:(key,value)=>map.set(key,value)};};
function environment(){const dom=installDOM(),before={sessionStorage:globalThis.sessionStorage,localStorage:globalThis.localStorage};globalThis.sessionStorage=storage();globalThis.localStorage=storage();return {...dom,restore(){dom.restore();Object.assign(globalThis,before);}};}
const selection=()=>({anchor:vector.prepared.anchor,prepare:vector.prepare_body});
const prepared=payload=>{const query={...vector.prepared.reconcile.http.query};if(payload.request_id)query.request_id=payload.request_id;else delete query.request_id;return {...vector.prepared,reconcile:{http:{...vector.prepared.reconcile.http,query},requires:payload.request_id?[]:['request_id']}};};
const saved=payload=>({...vector.saved,request_id:payload.request_id,correction:{...vector.saved.correction,text:payload.text.trim(),anchor:payload.anchor},source_basis:payload.source_basis});
test('actual owner prepare descriptors preserve original source basis and Unicode payload during late typing',{skip:!vector},async()=>{
 const d=environment();try{const calls=[];let finish;const request=async(path,payload)=>{calls.push({path,payload});if(path==='/authoring/correction-prepare')return prepared(payload);if(path==='/authoring/correction')return new Promise(resolve=>finish=()=>resolve(saved(payload)));throw Error(path);};
 const dialog=await openFeedbackComment({project:'p',selection:selection(),request});const input=dialog.querySelector('textarea');input.value=vector.payload.text;input.oninput();const saving=findButton(dialog,'Save comment').click();while(!finish)await new Promise(resolve=>setTimeout(resolve,0));input.value='Newer text stays — όχι';input.oninput();finish();await saving;
 assert.equal(calls.length,2);assert.deepEqual(calls[1].payload.source_basis,vector.payload.source_basis);assert.equal(calls[1].payload.text,vector.payload.text);assert.equal(input.value,'Newer text stays — όχι');assert.match(dialog.textContent,/later typing remains/);dialog.close();
 }finally{d.restore();}
});
test('lost Save response uses exact pure owner lookup and never posts a second origin',{skip:!vector},async()=>{
 const d=environment();try{let posted=null,posts=0;const request=async(path,payload)=>{if(path==='/authoring/correction-prepare')return prepared(payload);if(path==='/authoring/correction'){posts++;posted=payload;throw Error('public lost response');}if(path.startsWith('/authoring/correction-request?'))return {...vector.lookup,request_id:posted.request_id,receipt:saved(posted)};throw Error(path);};
 const dialog=await openFeedbackComment({project:'p',selection:selection(),request}),input=dialog.querySelector('textarea');input.value=vector.payload.text;input.oninput();await findButton(dialog,'Save comment').click();assert.match(dialog.textContent,/lost response/);await findButton(dialog,'Check save').click();assert.equal(posts,1);assert.equal(input.value,vector.payload.text);assert.match(dialog.textContent,/Comment saved/);dialog.close();
 }finally{d.restore();}
});
test('review responses show the owner revision chain and comment status, and refuse a foreign chain',async()=>{
 const d=environment();try{
  const origin={project:'p',correction_id:'C-public'},get=url=>({http:{method:'GET',url}});
  const revision={schema_version:'laplace.feedback-revision-join/1',project:'p',turn_id:'WT-producer',state:'BUILT',
   links:{produced:true,applied:true,built:true,incomplete_applications:0,unattributed_applications:0},
   next_read:get('/authoring/build?project=p&build_job=%7B%7D'),
   proposals:[{version:'sha256:'+'1'.repeat(64),read:get('/authoring/proposal-preview?project=p&id=WT-producer&proposal_version=v&view=summary'),
    applications:[{id:'WA-good',read:get('/authoring/session-turn?project=p&id=WT-producer&view=application&item_id=WA-good'),source_effect:{state:'COMMITTED',complete:true},
     build:{state:'BUILT',build_job:{id:'BLD-1'},job_status_read:get('/authoring/build?project=p&build_job=%7B%7D')}}]}]};
  const aggregate=rev=>({schema_version:'laplace.feedback-route/1',project:'p',route_id:'FR-1',state:'response_ready',work:{id:'W',title:'Review'},
   origin:{origin_ref:origin,correction:{text:'Tighten this claim.',status:'addressed',status_history:[{status:'open'},{status:'addressed'}],status_note:'Fixed in source'},currentness:{state:'CURRENT'}},
   policy:{limits:{}},allowance:{},actions:{},read:{http:{method:'GET',url:'/work/delivery?project=p&request=%7B%7D'}},
   edges:[{edge_id:'FE-1',obligation_id:'claim',recipient:{label:'Reviewer'},event:{admitted:{session_id:'WS-producer',turn_id:'WT-producer'},state:'ADMITTED'},revision:rev}]});
  let value=aggregate(revision),preview=null;const calls=[],request=async(path,payload)=>{calls.push({path:String(path),payload});
   if(String(path).startsWith('/authoring/proposal-preview?'))return structuredClone(preview);
   if(String(path).startsWith('/authoring/build?'))return {project:'p',state:'idle',fresh:true,job_basis_current:false};
   return structuredClone(value);};
  const settle=async()=>{for(let i=0;i<10;i++)await new Promise(resolve=>setTimeout(resolve,0));};
  const dialog=await openFeedbackResponses({project:'p',origin,workId:'W',read:null,request});
  const text=dialog.textContent;
  assert.match(text,/Revision chain/);assert.match(text,/a recorded build shows these exact bytes/);
  assert.match(text,/Read proposal/);assert.match(text,/Read application WA-good/);assert.match(text,/Read build status BLD-1/);
  assert.match(text,/none is your disposition of the comment/);
  assert.match(text,/Comment status: addressed · 2 recorded status changes/);assert.match(text,/not acceptance of any revision/);
  // Inspect opens the exact produced version read-only through the existing walk.showProposal path
  const version='sha256:'+'1'.repeat(64),inspect=dialog.querySelector('[data-revision-inspect="'+version+'"]');assert.ok(inspect,'the Inspect control names the exact produced version');
  const shown=[];globalThis.walk={showProposal:(proposal,options)=>shown.push({proposal,options})};
  try{
   preview={proposal_version:version,edits:[]};await inspect.click();await settle();
   const asked=calls.find(call=>call.path.startsWith('/authoring/proposal-preview?'));assert.ok(asked&&asked.payload===undefined,'a GET read, never a POST');
   const query=new URL(asked.path,'http://local').searchParams;assert.equal(query.get('project'),'p');assert.equal(query.get('turn_id'),'WT-producer');assert.equal(query.get('proposal_version'),version);
   assert.equal(shown.length,1);assert.equal(shown[0].options.readOnly,true);assert.equal(shown[0].proposal.proposal_version,version);
   preview={proposal_version:'sha256:'+'9'.repeat(64)};await inspect.click();await settle();
   assert.equal(shown.length,1,'another returned version is never shown');assert.match(dialog.textContent,/returned another version; nothing was shown/);
   // closure 2026-11-02: without the canonical project Review controller this view cannot decide; it never flips walk to editable
   preview={proposal_version:version,edits:[]};const decide=dialog.querySelector('[data-revision-decide="'+version+'"]');assert.ok(decide,'the decision route names the exact version');await decide.click();await settle();
   assert.equal(shown.length,1,'no editable walk.showProposal without the canonical decision owner');assert.match(dialog.textContent,/cannot decide proposals/);
  }finally{delete globalThis.walk;}
  // the BUILT fact is checked through the build owner's job status; a moved basis is said, not hidden
  const check=dialog.querySelector('[data-revision-build="BLD-1"]');assert.ok(check,'the build check is the exact chain build job');await check.click();await settle();
  assert.match(dialog.textContent,/job basis is today's source: no/);assert.match(dialog.textContent,/would not show these exact bytes/);
  assert.ok(calls.every(call=>call.payload===undefined),'inspecting the chain never posts');
  dialog.close();
  value=aggregate({...revision,turn_id:'WT-foreign'});
  const refused=await openFeedbackResponses({project:'p',origin,workId:'W',read:null,request});
  assert.match(refused.textContent,/another project or producer turn/);assert.doesNotMatch(refused.textContent,/Revision chain/);refused.close();
 }finally{d.restore();}
});
test('review responses decide through the canonical project Review controller with exact identity; a refusal keeps the dialog',async()=>{
 const d=environment();try{
  const origin={project:'p',correction_id:'C-public'},get=url=>({http:{method:'GET',url}}),version='sha256:'+'1'.repeat(64);
  const read=get('/authoring/proposal-preview?project=p&id=WT-producer&proposal_version='+version+'&view=summary');
  const revision={schema_version:'laplace.feedback-revision-join/1',project:'p',turn_id:'WT-producer',state:'NOT_APPLIED',
   links:{produced:true,applied:false,built:false,incomplete_applications:0,unattributed_applications:0},next_read:read,proposals:[{version,read,applications:[]}]};
  const value={schema_version:'laplace.feedback-route/1',project:'p',route_id:'FR-1',state:'response_ready',work:{id:'W',title:'Review'},
   origin:{origin_ref:origin,correction:{text:'Tighten this claim.',status:'open'},currentness:{state:'CURRENT'}},policy:{limits:{}},allowance:{},actions:{},
   read:{http:{method:'GET',url:'/work/delivery?project=p&request=%7B%7D'}},
   edges:[{edge_id:'FE-1',obligation_id:'claim',recipient:{label:'Writer'},event:{admitted:{session_id:'WS-producer',turn_id:'WT-producer'},state:'ADMITTED'},revision}]};
  const calls=[],request=async path=>{calls.push(String(path));if(String(path).startsWith('/authoring/proposal-preview?'))return {proposal_version:version,edits:[]};return structuredClone(value);};
  const settle=async()=>{for(let i=0;i<10;i++)await new Promise(resolve=>setTimeout(resolve,0));};
  const shown=[];globalThis.walk={showProposal:(proposal,options)=>shown.push({proposal,options})};
  try{
   let refuse=true;const opened=[];
   const openProposal=async(turnId,choice)=>{opened.push({turnId,choice:structuredClone(choice)});if(refuse)throw Error('Unsaved manuscript changes would be replaced; save or discard them first.');};
   const dialog=await openFeedbackResponses({project:'p',origin,workId:'W',read:null,request,openProposal});
   const decide=dialog.querySelector('[data-revision-decide="'+version+'"]');assert.ok(decide,'the decision route names the exact version');
   await decide.click();await settle();
   assert.equal(opened.length,1);assert.deepEqual(opened[0],{turnId:'WT-producer',choice:{proposalVersion:version,readHandle:read,readOnly:false,decision:true}});
   assert.notEqual(dialog.isConnected,false,'a canonical refusal (draft/permission) keeps the responses dialog');assert.match(dialog.textContent,/Unsaved manuscript changes/);
   refuse=false;await decide.click();await settle();
   assert.equal(opened.length,2);assert.equal(shown.length,0,'the canonical controller, not this view, shows the decision');
   assert.ok(calls.every(path=>!path.startsWith('/authoring/apply')&&!path.startsWith('/authoring/proposal-decision')),'this view never decides or applies');
  }finally{delete globalThis.walk;}
 }finally{d.restore();}
});
test('a7 fresh comment Save adopts its actual saved origin in the same editor and requests reviews with separate custody',{skip:!vector},async()=>{
 const d=environment();try{
  const posts=[];let finish,lose=true,receipt=null,rid=null;const get=url=>({http:{method:'GET',url}});
  const policy={mode:'manual',recipients:[{obligation_id:'claim',recipient_binding_id:'RB-1'}],limits:{max_new_admissions:1,max_attempts:1,admission_seconds:60,runtime_seconds:60}};
  const statusRead=id=>get('/work/delivery?'+new URLSearchParams({project:'p',request:JSON.stringify({action:'route-status',work_id:'W',request_id:id})}));
  const request=async(path,payload)=>{const url=new URL(String(path),'http://local');
   if(url.pathname==='/authoring/correction-prepare')return prepared(payload);
   if(url.pathname==='/authoring/correction'){posts.push({path:url.pathname,payload});return new Promise(resolve=>finish=()=>{receipt=saved(payload);resolve(receipt);});}
   if(url.pathname==='/work/state')return {project:'p',tasks:[{id:'W',title:'Review claim'}],read_cut:{revision:'r1'}};
   if(url.pathname==='/work/delivery'&&payload===undefined){const read=JSON.parse(url.searchParams.get('request'));
    if(read.action==='route-preview'){assert.deepEqual(read.origin,receipt.origin_ref,'the review route is configured against the actual saved origin');rid=read.request_id;
     return {work:{id:'W',revision:'w1',title:'Review claim'},policy:null,policies:[],obligations:[{id:'claim',label:'Claim support',scope:'passage'}],bindings:[{id:'RB-1',label:'Approved reviewer'}],
      selected_recipients:policy.recipients,recipients:[],issues:[],actions:{compose:{permitted:true,route_spec:{action:'route-submit',work_id:'W',request_id:rid,expected_work_revision:'w1',policy}}},request_read:statusRead(rid)};}
    if(read.action==='route-status'){assert.equal(read.request_id,rid);return {effect:'RECORDED',route_id:'FR-1',aggregate:{schema_version:'laplace.feedback-route/1',project:'p',route_id:'FR-1',work:{id:'W'},origin:{origin_ref:receipt.origin_ref},policy}};}}
   if(url.pathname==='/work/delivery'){posts.push({path:url.pathname,payload});if(lose){lose=false;throw Error('public lost review acknowledgement');}}
   throw Error('UNRECORDED '+path);};
  const settle=async()=>{for(let i=0;i<10;i++)await new Promise(resolve=>setTimeout(resolve,0));};
  const dialog=await openFeedbackComment({project:'p',selection:selection(),request}),input=dialog.querySelector('textarea');
  input.value=vector.payload.text;input.oninput();const saving=findButton(dialog,'Save comment').click();while(!finish)await new Promise(resolve=>setTimeout(resolve,0));
  input.value='Later unsaved words';input.oninput();finish();await saving;await settle();
  assert.notEqual(dialog.isConnected,false,'the same editor stays open');assert.equal(d.dialogs().length,1,'no closed/reopened editor');
  assert.match(dialog.textContent,/later typing remains/);assert.match(dialog.textContent,/request reviews of this saved comment here/);
  assert.equal(input.value,'Later unsaved words','late typing stays an unsaved draft');
  const route=dialog.querySelector('details');route.open=true;await route.ontoggle();await settle();
  const work=dialog.querySelector('[aria-label="Existing review Work"]');work.value='W';await work.onchange();await settle();
  assert.match(dialog.textContent,/Claim support/);
  const send=findButton(dialog,'Request reviews');assert.equal(send.disabled,false,'reviews are requested against the adopted origin in this editor');
  await send.click();await settle();assert.match(dialog.textContent,/lost review acknowledgement/);
  await findButton(dialog,'Check review request').click();await settle();
  const routePosts=posts.filter(row=>row.path==='/work/delivery');
  assert.equal(routePosts.length,1,'a lost acknowledgement is reconciled by the exact lookup, never a second POST');
  assert.deepEqual(routePosts[0].payload.origin,receipt.origin_ref);assert.equal(routePosts[0].payload.request_id,rid);
  assert.equal(posts.filter(row=>row.path==='/authoring/correction').length,1,'one Save');
  assert.match(dialog.textContent,/Review route recorded/);assert.ok(findButton(dialog,'Review responses'));
  const key=name=>'laplace:feedback-route:'+JSON.stringify(['p',name]);
  const saveState=JSON.parse(globalThis.sessionStorage.getItem(key('passage-comment'))).state,routeState=JSON.parse(globalThis.sessionStorage.getItem(key('origin:'+JSON.stringify(receipt.origin_ref)))).state;
  assert.equal(saveState.receipt.origin_ref.correction_id,receipt.origin_ref.correction_id,'the settled Save keeps its own custody');assert.equal(saveState.pending,null);
  assert.equal(routeState.pending,null);assert.equal(routeState.receipt.route_id,'FR-1');assert.equal(routeState.unsaved_text,'Later unsaved words');
  assert.equal(input.value,'Later unsaved words');dialog.close();
  // F4: close and reopen the saved comment (its origin-keyed draft): the unsent later typing is visibly recovered, the
  // saved instruction stays the saved text, read-only, and nothing is posted.
  const postsBefore=posts.length;
  const reopened=await openFeedbackComment({project:'p',selection:selection(),request,existingOrigin:{origin_ref:receipt.origin_ref,correction:receipt.correction,
   source_basis:receipt.source_basis,review_route_spec:{work_id:'W'},review_route_read:null}});await settle();
  assert.match(reopened.textContent,/Unsent later typing/);assert.ok(reopened.textContent.includes('Later unsaved words'));
  const savedBox=reopened.querySelector('textarea');assert.equal(savedBox.value,receipt.correction.text);assert.equal(savedBox.readOnly,true);
  assert.equal(posts.length,postsBefore,'reopening posts nothing');assert.ok(findButton(reopened,'Review responses'),'the recorded route stays reachable');
  reopened.close();
 }finally{d.restore();}
});
test('a7 late typing during Save is recovered after close and reopen without routing or further typing',{skip:!vector},async()=>{
 const d=environment();try{
  const posts=[];let finish,receipt=null;
  const request=async(path,payload)=>{const url=new URL(String(path),'http://local');
   if(url.pathname==='/authoring/correction-prepare')return prepared(payload);
   if(url.pathname==='/authoring/correction'){posts.push(payload);return new Promise(resolve=>finish=()=>{receipt=saved(payload);resolve(receipt);});}
   throw Error('UNRECORDED '+path);};
  const dialog=await openFeedbackComment({project:'p',selection:selection(),request}),input=dialog.querySelector('textarea');
  input.value=vector.payload.text;input.oninput();const saving=findButton(dialog,'Save comment').click();while(!finish)await new Promise(resolve=>setTimeout(resolve,0));
  input.value='Typed while saving';input.oninput();finish();await saving;
  dialog.close();
  const reopened=await openFeedbackComment({project:'p',selection:selection(),request,existingOrigin:{origin_ref:receipt.origin_ref,correction:receipt.correction,
   source_basis:receipt.source_basis,review_route_spec:null,review_route_read:null}});
  assert.match(reopened.textContent,/Unsent later typing/);assert.ok(reopened.textContent.includes('Typed while saving'));
  const box=reopened.querySelector('textarea');assert.equal(box.value,receipt.correction.text);assert.equal(box.readOnly,true);
  assert.equal(posts.length,1,'one Save; reopening posts nothing');reopened.close();
 }finally{d.restore();}
});
test('a7 response revision chain shows the actual resolved successor separately and never posts',{skip:!routeVector},async()=>{
 const d=environment();try{
  const v=routeVector,origin={project:'fixture',correction_id:'C-a7'},calls=[];
  const edge={edge_id:'FE-a7',obligation_id:'claim',obligation:{state:'AUTHORED_SNAPSHOT',id:'claim',label:'Claim support',scope:'passage'},recipient:{label:'Writer'},
   event:{admitted:{session_id:'WS-a7',turn_id:v.turn_id},state:'ADMITTED'},revision:v.built};
  const value={schema_version:'laplace.feedback-route/1',project:'fixture',route_id:'FR-a7',state:'waiting',work:{id:'W',title:'Review'},
   origin:{origin_ref:origin,correction:{text:'Resolve the passage.',status:'open'},currentness:{state:'CURRENT'}},policy:{limits:{}},allowance:{},actions:{},
   read:{http:{method:'GET',url:'/work/delivery?project=fixture&request=%7B%7D'}},edges:[edge]};
  const request=async(path,payload)=>{calls.push({path:String(path),payload});return structuredClone(value);};
  const dialog=await openFeedbackResponses({project:'fixture',origin,workId:'W',read:null,request});const text=dialog.textContent;
  assert.match(text,/A proposal was produced; it has not been applied\./,'the original version direct fact stays');
  assert.ok(text.includes('Resolved successor '+v.successor_ref.id),'the actual successor is shown by its exact id');
  assert.match(text,/The original version itself stays unapplied/);
  const appLink=dialog.querySelector('[data-revision-link="successor-application"]');
  assert.ok(appLink&&String(appLink.href).includes('/authoring/history?')&&!String(appLink.href).includes('session-turn'),'the successor application link is its journal record read');
  assert.match(text,/Successor application \S+: source effect \w+ \(complete\) · build built/);
  assert.match(text,/Review focus: Claim support · passage/);assert.match(text,/Obligation claim/);
  assert.ok(calls.every(call=>call.payload===undefined),'read-only inspection never posts');
  dialog.close();
  const foreign=structuredClone(v.built);for(const proposal of foreign.proposals)for(const item of proposal.resolved_successors?.items||[])item.predecessor.turn_id='WT-foreign';
  value.edges=[{...edge,revision:foreign}];
  const refused=await openFeedbackResponses({project:'fixture',origin,workId:'W',read:null,request});
  assert.match(refused.textContent,/another predecessor turn/);assert.doesNotMatch(refused.textContent,/Resolved successor/);refused.close();
  value.edges=[{...edge,obligation:{state:'LEGACY_UNSNAPSHOTTED',id:'claim',label:null,scope:null},revision:v.built}];
  const legacy=await openFeedbackResponses({project:'fixture',origin,workId:'W',read:null,request});
  assert.match(legacy.textContent,/Review focus: the recorded question of this request · inspect handed inputs; the current Work question is not substituted/);
  assert.doesNotMatch(legacy.textContent,/Claim support/);assert.match(legacy.textContent,/Obligation claim · legacy unsnapshotted/);legacy.close();
  assert.ok(calls.every(call=>call.payload===undefined),'read-only inspection never posts');
 }finally{d.restore();}
});
// Fresh-slot recovery: A is the earlier passage (its preparation refuses like the rendered-math quote did), B is a
// later plain selection. The owner responses are the exact public vector shapes; anchors echo the request.
const REFUSED='Displayed quote is not an exact selection inside the inspected source extent; retain the draft and compare explicitly.';
const selectionB=()=>{const a=selection(),anchor={...a.anchor,quote:'A different plain passage.'};return {anchor,prepare:{...a.prepare,anchor:{...(a.prepare.anchor||a.anchor),quote:'A different plain passage.'}}};};
const echoed=payload=>({...prepared(payload),anchor:{...vector.prepared.anchor,...(payload.anchor||{})}});
const withRead=receipt=>({...receipt,read:receipt.read||{http:{method:'GET',url:'/authoring/correction-origin?'+new URLSearchParams({project:'p',origin_ref:JSON.stringify(receipt.origin_ref)})}}});
const settleTicks=async()=>{for(let i=0;i<12;i++)await new Promise(resolve=>setTimeout(resolve,0));};
function recoveryOwner({refuseA=true}={}){
 const calls=[];let delayA=null;
 const request=async(path,payload)=>{calls.push({path:String(path),payload});
  if(path==='/authoring/correction-prepare'){const isB=payload?.anchor?.quote==='A different plain passage.'||!!payload?.anchor?.source_selection;
   if(!isB&&delayA)return delayA.promise;if(!isB&&refuseA)throw Error(REFUSED);return echoed(payload);}
  if(path==='/authoring/correction')return withRead(saved(payload));
  throw Error('UNRECORDED '+path);};
 return {calls,request,delay(){let resolve,reject;const promise=new Promise((done,fail)=>{resolve=done;reject=fail;});delayA={promise,resolve,reject};return delayA;},
  posts:()=>calls.filter(call=>call.path==='/authoring/correction'),prepares:()=>calls.filter(call=>call.path==='/authoring/correction-prepare')};
}
test('comment empty refused draft offers the newly selected passage, then prepares and saves it exactly once',{skip:!vector},async()=>{
 const d=environment();try{
  const owner=recoveryOwner();
  const first=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  assert.match(first.textContent,/Displayed quote is not an exact selection/);
  // The refused draft is retained empty (as after Prepare another or erased typing): nothing unsent, nothing pending.
  const typed=first.querySelector('textarea');typed.value='x';typed.oninput();typed.value='';typed.oninput();first.close();
  const dialog=await openFeedbackComment({project:'p',selection:selectionB(),request:owner.request});await settleTicks();
  assert.match(dialog.textContent,/new selection was not substituted/);assert.equal(findButton(dialog,'Save comment').disabled,true);
  await findButton(dialog,'Use the newly selected passage').click();await settleTicks();
  const last=owner.prepares().at(-1);assert.equal(last.payload.anchor.quote,'A different plain passage.');
  assert.match(dialog.textContent,/A different plain passage\./);assert.match(dialog.textContent,/Comment target: the quoted text/);
  const input=dialog.querySelector('textarea');input.value='Clarify this plain claim.';input.oninput();
  await findButton(dialog,'Save comment').click();await settleTicks();
  assert.equal(owner.posts().length,1,'exactly one Save');assert.equal(owner.posts()[0].payload.anchor.quote,'A different plain passage.');
  assert.equal(owner.posts()[0].payload.text,'Clarify this plain claim.');dialog.close();
 }finally{d.restore();}
});
test('comment unsent text is never moved without a choice; Move keeps the text on the new passage and posts nothing',{skip:!vector},async()=>{
 const d=environment();try{
  const owner=recoveryOwner();
  const first=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  const input=first.querySelector('textarea');input.value='Keep this instruction.';input.oninput();first.close();
  const dialog=await openFeedbackComment({project:'p',selection:selectionB(),request:owner.request});await settleTicks();
  for(const label of ['Keep it on the earlier passage','Move it to the newly selected passage','Copy it aside and start on the newly selected passage','Discard it and use the newly selected passage'])assert.ok(findButton(dialog,label),label);
  assert.equal(owner.prepares().some(call=>call.payload.anchor.quote==='A different plain passage.'),false,'nothing was retargeted yet');
  await findButton(dialog,'Move it to the newly selected passage').click();await settleTicks();
  assert.equal(owner.prepares().at(-1).payload.anchor.quote,'A different plain passage.');
  assert.equal(dialog.querySelector('textarea').value,'Keep this instruction.');assert.equal(owner.posts().length,0);dialog.close();
  const copied=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  await findButton(copied,'Copy it aside and start on the newly selected passage').click();await settleTicks();
  assert.equal(copied.querySelector('textarea').value,'');assert.match(copied.textContent,/Your earlier unsent text/);assert.match(copied.textContent,/Keep this instruction\./);
  assert.equal(owner.posts().length,0);copied.close();
 }finally{d.restore();}
});
test('comment pending UNKNOWN Save and corrupt recovery are never retargeted by a new selection',{skip:!vector},async()=>{
 const d=environment();try{
  const calls=[];let lose=true;
  const request=async(path,payload)=>{calls.push({path,payload});if(path==='/authoring/correction-prepare')return echoed(payload);
   if(path==='/authoring/correction'){if(lose){lose=false;throw Error('public lost response');}return withRead(saved(payload));}
   if(String(path).startsWith('/authoring/correction-request?'))return {...vector.lookup,request_id:calls.find(c=>c.path==='/authoring/correction').payload.request_id,receipt:withRead(saved(calls.find(c=>c.path==='/authoring/correction').payload))};
   throw Error('UNRECORDED '+path);};
  const first=await openFeedbackComment({project:'p',selection:selection(),request});await settleTicks();
  const input=first.querySelector('textarea');input.value='Unconfirmed instruction.';input.oninput();
  await findButton(first,'Save comment').click();await settleTicks();first.close();
  const dialog=await openFeedbackComment({project:'p',selection:selectionB(),request});await settleTicks();
  assert.match(dialog.textContent,/still unconfirmed/);assert.ok(!dialog.querySelector('[data-recovery]'),'no retarget, keep or discard offer');
  await findButton(dialog,'Check save').click();await settleTicks();
  assert.equal(calls.filter(c=>c.path==='/authoring/correction').length,1,'the exact original request is reconciled, not resent');
  assert.match(dialog.textContent,/Comment saved/);dialog.close();
  globalThis.sessionStorage.setItem('laplace:feedback-route:'+JSON.stringify(['p','passage-comment']),'{damaged');
  globalThis.localStorage.setItem('laplace:feedback-route:'+JSON.stringify(['p','passage-comment']),'{damaged');
  const damaged=await openFeedbackComment({project:'p',selection:selectionB(),request});await settleTicks();
  assert.match(damaged.textContent,/Retained unreadable comment recovery/);assert.ok(!damaged.querySelector('[data-recovery]'));
  assert.equal(globalThis.sessionStorage.getItem('laplace:feedback-route:'+JSON.stringify(['p','passage-comment'])),'{damaged','damaged recovery is not cleared');damaged.close();
 }finally{d.restore();}
});
test('comment restored saved receipt opens the same owner-verified origin with Request reviews and never saves again',{skip:!vector},async()=>{
 const d=environment();try{
  const owner=recoveryOwner({refuseA:false});let originReads=0;
  const request=async(path,payload)=>{if(String(path).startsWith('/authoring/correction-origin?')){originReads++;const receipt=withRead(saved(owner.posts()[0].payload));return {origin_ref:receipt.origin_ref,correction:receipt.correction,source_basis:receipt.source_basis};}return owner.request(path,payload);};
  const first=await openFeedbackComment({project:'p',selection:selection(),request});await settleTicks();
  const input=first.querySelector('textarea');input.value=vector.payload.text;input.oninput();
  await findButton(first,'Save comment').click();await settleTicks();first.close();
  // A storage-restored fresh slot: the held Save receipt is under the passage key, opened by a new selection.
  const dialog=await openFeedbackComment({project:'p',selection:selectionB(),request});await settleTicks();
  assert.equal(findButton(dialog,'Save comment').disabled,true,'a restored receipt is never resaved');
  await findButton(dialog,'Open saved comment and request reviews').click();await settleTicks();
  assert.equal(originReads,1);assert.match(dialog.textContent,/Saved comment opened/);
  const box=dialog.querySelector('textarea');assert.equal(box.readOnly,true);assert.equal(box.value,owner.posts()[0].payload.text.trim());
  assert.ok(findButton(dialog,'Request reviews'),'the saved origin offers Request reviews');assert.equal(owner.posts().length,1,'no second Save');dialog.close();
 }finally{d.restore();}
});
test('comment delayed earlier prepare cannot overwrite the newly chosen passage',{skip:!vector},async()=>{
 const d=environment();try{
  const owner=recoveryOwner();
  const first=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  const typed=first.querySelector('textarea');typed.value='x';typed.oninput();typed.value='';typed.oninput();first.close();
  const late=owner.delay();
  const opening=openFeedbackComment({project:'p',selection:selectionB(),request:owner.request});await settleTicks();
  const dialog=d.dialogs().at(-1);assert.equal(owner.prepares().length,2,'the earlier passage is still being re-inspected');
  await findButton(dialog,'Use the newly selected passage').click();await settleTicks();
  late.resolve(echoed({...selection().prepare,anchor:selection().anchor}));await settleTicks();await opening;
  const input=dialog.querySelector('textarea');input.value='Only for the new passage.';input.oninput();
  await findButton(dialog,'Save comment').click();await settleTicks();
  assert.equal(owner.posts().length,1);assert.equal(owner.posts()[0].payload.anchor.quote,'A different plain passage.','the late earlier reply did not replace the chosen target');
  dialog.close();
 }finally{d.restore();}
});
test('comment mapping refusal offers an explicit whole-paragraph source target, never a silent widening',{skip:!vector},async()=>{
 const d=environment();try{
  const owner=recoveryOwner();
  const whole={schema:'laplace.comment-source-selection/1',kind:'whole-block',units:'unicode-codepoints',start:0,end:120,display_quote:'The file observations.csv contains (x,y)=(0,0).'};
  const a=selection(),wholeAnchor={...a.anchor,source_selection:whole};delete wholeAnchor.quote;
  const mapped={...a,mapping:{refused:'inside-math',reason:'This selection starts or ends inside rendered math; comment on the whole paragraph or select the whole formula.',choices:[{label:'Comment on the whole paragraph',anchor:wholeAnchor}]}};
  const dialog=await openFeedbackComment({project:'p',selection:mapped,request:owner.request});await settleTicks();
  assert.match(dialog.textContent,/inside rendered math/);assert.equal(owner.prepares().filter(c=>c.payload.anchor.source_selection).length,0,'no silent widening');
  await findButton(dialog,'Comment on the whole paragraph').click();await settleTicks();
  const asked=owner.prepares().at(-1).payload.anchor;assert.deepEqual(asked.source_selection,whole);assert.ok(!('quote' in asked));
  assert.match(dialog.textContent,/Comment target: the whole paragraph source/);
  const input=dialog.querySelector('textarea');input.value='Check the mean.';input.oninput();await findButton(dialog,'Save comment').click();await settleTicks();
  assert.equal(owner.posts().length,1);assert.deepEqual(owner.posts()[0].payload.anchor.source_selection,whole);dialog.close();
 }finally{d.restore();}
});
// Review 276bdce0 F1: an owner that WOULD accept the rendered quote still sees no prepare until an explicit qualified choice.
test('comment mapping refusal never prepares the rendered quote, even for an owner that would accept it',{skip:!vector},async()=>{
 const d=environment();try{
  const owner=recoveryOwner({refuseA:false});
  const whole={schema:'laplace.comment-source-selection/1',kind:'whole-block',units:'unicode-codepoints',start:0,end:120,display_quote:'The file observations.csv contains (x,y)=(0,0).'};
  const a=selection(),wholeAnchor={...a.anchor,source_selection:whole};delete wholeAnchor.quote;
  const mapped={...a,mapping:{refused:'multi-source',reason:'This selection crosses paragraphs; a comment targets one paragraph. Choose the paragraph to comment on, or select text within one paragraph.',choices:[{label:'Comment on the whole of paragraph 1 (lines 3)',anchor:wholeAnchor,expected:['choice-identity']}]}};
  const dialog=await openFeedbackComment({project:'p',selection:mapped,request:owner.request});await settleTicks();
  assert.equal(owner.prepares().length,0,'the refused selection prepares nothing, although this owner would accept its rendered quote');
  assert.match(dialog.textContent,/crosses paragraphs/);assert.match(dialog.textContent,/No comment target yet/);assert.match(dialog.textContent,/no qualified source target yet/);
  assert.equal(findButton(dialog,'Save comment').disabled,true);
  const input=dialog.querySelector('textarea');input.value='Typed before choosing.';input.oninput();assert.equal(owner.prepares().length,0);
  await findButton(dialog,'Comment on the whole of paragraph 1 (lines 3)').click();await settleTicks();
  assert.equal(owner.prepares().length,1,'exactly one prepare, for the explicit choice');const asked=owner.prepares()[0].payload;
  assert.deepEqual(asked.anchor.source_selection,whole);assert.ok(!('quote' in asked.anchor));assert.deepEqual(asked.expected,['choice-identity']);
  assert.match(dialog.textContent,/Comment target: the whole paragraph source/);assert.equal(dialog.querySelector('textarea').value,'Typed before choosing.');
  await findButton(dialog,'Save comment').click();await settleTicks();
  assert.equal(owner.posts().length,1);assert.deepEqual(owner.posts()[0].payload.anchor.source_selection,whole);assert.equal(owner.posts()[0].payload.text,'Typed before choosing.');dialog.close();
 }finally{d.restore();}
});
// Review 30e422e0 findings 1/2 and Root disposition aefa8d48: restored-receipt adoption hands fresh unsent text to the
// origin draft once and shows that draft's retained unsent text at once; competing versions need an explicit choice; a
// failed hand-over moves nothing. Owner reads/writes are the public vector shapes; storage is the environment's own.
const restoredRoute=()=>{const owner=recoveryOwner({refuseA:false});let reads=0;
 const origin=()=>{const receipt=withRead(saved(owner.posts()[0].payload));return {origin_ref:receipt.origin_ref,correction:receipt.correction,source_basis:receipt.source_basis};};
 const request=async(path,payload)=>{if(String(path).startsWith('/authoring/correction-origin?')){reads++;return origin();}return owner.request(path,payload);};
 return {owner,request,origin,reads:()=>reads,key:()=>'laplace:feedback-route:'+JSON.stringify(['p','origin:'+JSON.stringify(origin().origin_ref)])};};
const saveOnce=async route=>{const first=await openFeedbackComment({project:'p',selection:selection(),request:route.request});await settleTicks();
 const input=first.querySelector('textarea');input.value=vector.payload.text;input.oninput();await findButton(first,'Save comment').click();await settleTicks();first.close();};
const reopenFresh=async route=>{const dialog=await openFeedbackComment({project:'p',selection:selectionB(),request:route.request});await settleTicks();return dialog;};
const seedOriginUnsent=(route,value)=>{const stored=JSON.parse(globalThis.sessionStorage.getItem(route.key()));assert.ok(stored?.state,'the live Save retained its origin draft');
 stored.state.unsaved_text=value;for(const store of [globalThis.sessionStorage,globalThis.localStorage])store.setItem(route.key(),JSON.stringify(stored));};
const failOriginWrites=route=>{const key=route.key(),undo=[];for(const store of [globalThis.sessionStorage,globalThis.localStorage]){const real=store.setItem;
  store.setItem=function(name,value){if(name===key)throw Error('storage quota exceeded');return real.call(this,name,value);};undo.push(()=>{store.setItem=real;});}return ()=>undo.forEach(fn=>fn());};
test('comment repeated restored-receipt adoption never re-appends the stale fresh fragment; the newest unsent text stays exact',{skip:!vector},async()=>{
 const d=environment();try{
  const route=restoredRoute();await saveOnce(route);
  let dialog=await reopenFresh(route),box=dialog.querySelector('textarea');box.value='L';box.oninput();
  await findButton(dialog,'Open saved comment and request reviews').click();await settleTicks();
  assert.equal(box.value,'L');box.value='L M';box.oninput();dialog.close();
  let newest='L M';
  for(const round of [1,2]){
   dialog=await reopenFresh(route);box=dialog.querySelector('textarea');assert.equal(box.value,'L','the fresh slot keeps the fragment it already handed over');
   await findButton(dialog,'Open saved comment and request reviews').click();await settleTicks();
   assert.equal(box.value,newest,'round '+round+': the newest unsent text is exact, with no stale fragment appended');
   assert.ok(!box.value.includes('\n\nL'));assert.doesNotMatch(dialog.textContent,/Two unsent versions/);
   newest+=' N'+round;box.value=newest;box.oninput();dialog.close();}
  assert.equal(route.owner.posts().length,1,'no second Save');assert.equal(route.reads(),3);
 }finally{d.restore();}
});
test('comment restored saved receipt shows the stored origin unsent note at once, with no fresh typing',{skip:!vector},async()=>{
 const d=environment();try{
  const route=restoredRoute();await saveOnce(route);seedOriginUnsent(route,'Earlier unsent note.');
  const dialog=await reopenFresh(route),box=dialog.querySelector('textarea');assert.equal(box.value.trim(),route.origin().correction.text);
  await findButton(dialog,'Open saved comment and request reviews').click();await settleTicks();
  assert.equal(box.value,'Earlier unsent note.','the retained unsent note is visible immediately');assert.equal(box.readOnly,false);
  assert.ok(dialog.textContent.includes(route.origin().correction.text),'the saved comment is shown unchanged and distinct');
  assert.ok(findButton(dialog,'Request reviews'));assert.equal(route.owner.posts().length,1,'no second Save');dialog.close();
 }finally{d.restore();}
});
test('comment restored-receipt hand-over keeps custody on a storage failure and needs an explicit choice between competing unsent versions',{skip:!vector},async()=>{
 const d=environment();try{
  const route=restoredRoute();await saveOnce(route);
  let dialog=await reopenFresh(route),box=dialog.querySelector('textarea');box.value='Fresh text.';box.oninput();
  let restore=failOriginWrites(route);
  await findButton(dialog,'Open saved comment and request reviews').click();await settleTicks();restore();
  assert.match(dialog.textContent,/could not retain your unsent text/);assert.match(dialog.textContent,/Nothing was moved/);
  assert.equal(box.value,'Fresh text.');assert.equal(box.readOnly,false);assert.ok(findButton(dialog,'Open saved comment and request reviews'),'the hand-over can be retried');
  await findButton(dialog,'Open saved comment and request reviews').click();await settleTicks();
  assert.equal(box.value,'Fresh text.');assert.match(dialog.textContent,/Saved comment opened/);dialog.close();
  seedOriginUnsent(route,'Independently revised note.');
  dialog=await reopenFresh(route);box=dialog.querySelector('textarea');assert.equal(box.value,'Fresh text.');box.value='Fresh text, edited again.';box.oninput();
  await findButton(dialog,'Open saved comment and request reviews').click();await settleTicks();
  assert.match(dialog.textContent,/Two unsent versions/);assert.ok(dialog.textContent.includes('Independently revised note.'));assert.ok(dialog.textContent.includes('Fresh text, edited again.'));
  assert.equal(box.readOnly,true,'nothing is merged before a choice');
  restore=failOriginWrites(route);await findButton(dialog,'Keep both, saved comment\'s text first').click();await settleTicks();restore();
  assert.match(dialog.textContent,/Both unsent versions are kept/);assert.match(dialog.textContent,/Two unsent versions/);
  await findButton(dialog,'Use the text from this editor').click();await settleTicks();
  assert.equal(box.value,'Fresh text, edited again.');assert.equal(box.readOnly,false);assert.doesNotMatch(dialog.textContent,/Two unsent versions/);
  assert.equal(route.owner.posts().length,1,'no second Save');dialog.close();
  const reopened=await openFeedbackComment({project:'p',selection:selection(),existingOrigin:route.origin(),request:route.request});await settleTicks();
  assert.match(reopened.textContent,/Unsent later typing/);assert.ok(reopened.textContent.includes('Fresh text, edited again.'));assert.ok(!reopened.textContent.includes('Independently revised note.'));reopened.close();
 }finally{d.restore();}
});
// Review 30e422e0 finding 3: a one-paragraph selection running past the body is refused with the paragraph's own choice.
test('comment one-paragraph overhang refusal offers the whole paragraph and prepares nothing before that choice, even for a permissive owner',{skip:!vector},async()=>{
 const d=environment();try{
  const owner=recoveryOwner({refuseA:false});
  const whole={schema:'laplace.comment-source-selection/1',kind:'whole-block',units:'unicode-codepoints',start:0,end:120,display_quote:'The file observations.csv contains (x,y)=(0,0).'};
  const a=selection(),wholeAnchor={...a.anchor,source_selection:whole};delete wholeAnchor.quote;
  const mapped={...a,mapping:{refused:'outside-paragraph',reason:'This selection runs past the paragraph it starts in. Comment on the whole paragraph, or select text within it.',choices:[{label:'Comment on the whole paragraph',anchor:wholeAnchor}]}};
  const dialog=await openFeedbackComment({project:'p',selection:mapped,request:owner.request});await settleTicks();
  assert.equal(owner.prepares().length,0,'the permissive owner is never asked before the choice');assert.match(dialog.textContent,/runs past the paragraph/);
  assert.equal(findButton(dialog,'Save comment').disabled,true);
  await findButton(dialog,'Comment on the whole paragraph').click();await settleTicks();
  assert.equal(owner.prepares().length,1);assert.deepEqual(owner.prepares()[0].payload.anchor.source_selection,whole);assert.ok(!('quote' in owner.prepares()[0].payload.anchor));dialog.close();
 }finally{d.restore();}
});
// Review 276bdce0 F3: a late REJECTION of the earlier passage's prepare is fenced exactly like a late success.
test('comment delayed earlier prepare rejection cannot overwrite the newly chosen passage, status or choices',{skip:!vector},async()=>{
 const d=environment();try{
  const owner=recoveryOwner();
  const first=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  const typed=first.querySelector('textarea');typed.value='x';typed.oninput();typed.value='';typed.oninput();first.close();
  const late=owner.delay();
  const opening=openFeedbackComment({project:'p',selection:selectionB(),request:owner.request});await settleTicks();
  const dialog=d.dialogs().at(-1);assert.equal(owner.prepares().length,2,'the earlier passage is still being re-inspected');
  await findButton(dialog,'Use the newly selected passage').click();await settleTicks();
  assert.match(dialog.textContent,/Original passage inspected/);
  late.reject(Error('LATE EARLIER PASSAGE REFUSAL'));await settleTicks();await opening;
  assert.doesNotMatch(dialog.textContent,/LATE EARLIER PASSAGE REFUSAL/,'the stale rejection reaches no status');
  assert.match(dialog.textContent,/Original passage inspected/);assert.match(dialog.textContent,/Comment target: the quoted text/);
  assert.ok(!dialog.querySelector('[data-recovery]'),'no stale recovery choices are painted');
  const input=dialog.querySelector('textarea');input.value='Only for the new passage.';input.oninput();
  await findButton(dialog,'Save comment').click();await settleTicks();
  assert.equal(owner.posts().length,1);assert.equal(owner.posts()[0].payload.anchor.quote,'A different plain passage.');dialog.close();
 }finally{d.restore();}
});
// Root disposition 8d533e71 (review 54370423 finding 2): the two-store draft protocol. Each retained wire names its revision
// and the revisions it descends from; a newer copy kept only by the non-preferred store is recovered and reported, copies
// that do not descend from one another need an explicit choice, and every original byte is kept until then.
const portModule=()=>import('../src/laplace/web/static_shared/feedback-route-port.mjs');
const memoryStore=()=>{const map=new Map();const store={map,fail:false,getItem:key=>map.has(key)?map.get(key):null,setItem(key,value){if(store.fail)throw Error('storage quota exceeded');map.set(key,String(value));}};return store;};
const DRAFT_KEY='laplace:feedback-route:'+JSON.stringify(['p','passage-comment']);
test('comment draft storage recovers a newer copy kept only by the backup store and never claims an unretained write',async()=>{
 const {createFeedbackDraft}=await portModule();const session=memoryStore(),backup=memoryStore();
 const open=()=>createFeedbackDraft({project:'p',key:'passage-comment',initial:{text:''},storage:session,backup});
 let draft=open();draft.update({text:'First text.'});assert.equal(draft.retained,true);
 session.fail=true;draft.update({text:'Newer text.'});session.fail=false;assert.equal(draft.retained,true,'the backup store retained it');
 const staleSession=session.map.get(DRAFT_KEY),backupBytes=backup.map.get(DRAFT_KEY);assert.match(staleSession,/First text\./);
 draft=open();assert.equal(draft.snapshot().text,'Newer text.','the newer retained copy is recovered, not the stale preferred copy');
 assert.deepEqual(draft.recovered,{from:'backup',stale:'session'});assert.equal(draft.disagreement,null);
 assert.equal(session.map.get(DRAFT_KEY),staleSession,'reading rewrites nothing');assert.equal(backup.map.get(DRAFT_KEY),backupBytes);
 backup.fail=true;draft.update({text:'Newest, this tab only.'});backup.fail=false;
 draft=open();assert.equal(draft.snapshot().text,'Newest, this tab only.');assert.equal(draft.recovered,null);
 session.fail=backup.fail=true;draft.update({text:'Never retained.'});session.fail=backup.fail=false;
 assert.equal(draft.retained,false);assert.match(draft.storageError,/could not be retained/);
 draft=open();assert.equal(draft.snapshot().text,'Newest, this tab only.','only retained text is recovered');
});
test('comment draft storage keeps the exact pending wire, saved receipt, source target and request identity through single-store recovery',async()=>{
 const {createFeedbackDraft}=await portModule();const session=memoryStore(),backup=memoryStore();
 const open=()=>createFeedbackDraft({project:'p',key:'passage-comment',initial:{text:''},storage:session,backup});
 const target={anchor:{file:'main.tex',line_start:3,line_end:3,source_selection:{schema:'laplace.comment-source-selection/1',kind:'whole-block',units:'unicode-codepoints',start:0,end:57,display_quote:'x'}}};
 const pending={request_id:'FC-exact',wire:'{"project":"p","request_id":"FC-exact","text":"Exact."}',observation:'UNKNOWN',lookup:{http:{method:'GET',url:'/authoring/correction-request?project=p&request_id=FC-exact'}}};
 let draft=open();draft.update({text:'Exact.',selection:target,request_id:'FC-exact'});
 session.fail=true;draft.update({pending});session.fail=false;
 draft=open();const held=draft.snapshot();assert.deepEqual(held.pending,pending,'the exact retained wire survives');assert.equal(held.request_id,'FC-exact');assert.deepEqual(held.selection,target);
 const receipt={origin_ref:{id:'AC-1'},correction:{text:'Exact.'}};
 backup.fail=true;draft.settle(receipt);backup.fail=false;
 draft=open();assert.deepEqual(draft.snapshot().receipt,receipt);assert.equal(draft.snapshot().pending,null);assert.deepEqual(draft.snapshot().selection,target);assert.equal(draft.snapshot().request_id,'FC-exact');
});
test('comment draft storage shows disagreeing, legacy and corrupt copies for explicit recovery and keeps every original byte',async()=>{
 const {createFeedbackDraft}=await portModule();const session=memoryStore(),backup=memoryStore(),otherTab=memoryStore();
 const open=(store=session)=>createFeedbackDraft({project:'p',key:'passage-comment',initial:{text:''},storage:store,backup});
 const tabA=open();tabA.update({text:'Base.'});
 backup.fail=true;tabA.update({text:'Tab A.'});backup.fail=false;
 const tabB=open(otherTab);assert.equal(tabB.snapshot().text,'Base.');tabB.update({text:'Tab B.'});
 const bytes=()=>[session.map.get(DRAFT_KEY),backup.map.get(DRAFT_KEY)],before=bytes();
 let draft=open();assert.deepEqual(draft.disagreement.map(item=>[item.store,item.state.text]),[['session','Tab A.'],['backup','Tab B.']]);
 assert.equal(draft.persist(),false);draft.update({text:'typed during disagreement'});assert.deepEqual(bytes(),before,'nothing overwrites either copy');
 await assert.rejects(()=>draft.retain({},{}),/disagree/);
 assert.equal(draft.choose(1),true);draft=open();assert.equal(draft.snapshot().text,'Tab B.');assert.equal(draft.disagreement,null);
 const legacy=text=>JSON.stringify({schema_version:'laplace.feedback-route-draft/1',project:'p',key:'passage-comment',state:{text}});
 session.map.set(DRAFT_KEY,legacy('Legacy one.'));backup.map.set(DRAFT_KEY,legacy('Legacy two.'));
 draft=open();assert.deepEqual(draft.disagreement.map(item=>item.state.text),['Legacy one.','Legacy two.'],'legacy copies without lineage are never silently ordered');
 backup.map.set(DRAFT_KEY,legacy('Legacy one.'));draft=open();assert.equal(draft.snapshot().text,'Legacy one.');assert.equal(draft.disagreement,null);
 session.map.set(DRAFT_KEY,'{damaged');draft=open();assert.match(draft.recoveryError,/unreadable/);assert.deepEqual(draft.recoveryRaw,['{damaged']);
 assert.equal(draft.snapshot().text,'Legacy one.');assert.equal(draft.persist(),false);assert.equal(session.map.get(DRAFT_KEY),'{damaged');
});
test('comment editor shows the newer copy kept by shared storage and asks for an explicit choice when stored copies disagree',{skip:!vector},async()=>{
 const d=environment();try{
  const owner=recoveryOwner({refuseA:false});
  const first=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  let box=first.querySelector('textarea');box.value='Retained in both stores.';box.oninput();first.close();
  const tab=globalThis.sessionStorage,realSet=tab.setItem;tab.setItem=(key,value)=>{if(key===DRAFT_KEY)throw Error('storage quota exceeded');return realSet(key,value);};
  const second=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  box=second.querySelector('textarea');box.value='Newer, shared storage only.';box.oninput();second.close();tab.setItem=realSet;
  const third=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  assert.equal(third.querySelector('textarea').value,'Newer, shared storage only.','the newer retained text is shown, not the stale tab copy');
  assert.match(third.textContent,/Recovered the newer copy of this draft/);third.close();
  tab.setItem(DRAFT_KEY,JSON.stringify({schema_version:'laplace.feedback-route-draft/1',project:'p',key:'passage-comment',state:{text:'Independent tab text.',selection:selection()}}));
  const before=[tab.getItem(DRAFT_KEY),globalThis.localStorage.getItem(DRAFT_KEY)],prepares=owner.prepares().length;
  const fourth=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  assert.match(fourth.textContent,/Two stored copies of this comment draft/);assert.ok(fourth.textContent.includes('Independent tab text.'));assert.ok(fourth.textContent.includes('Newer, shared storage only.'));
  assert.equal(findButton(fourth,'Save comment').disabled,true);assert.equal(owner.prepares().length,prepares,'nothing is prepared before the choice');
  assert.deepEqual([tab.getItem(DRAFT_KEY),globalThis.localStorage.getItem(DRAFT_KEY)],before,'both original copies are kept');
  await findButton(fourth,'Continue with the copy from shared browser storage; the other copy is replaced').click();await settleTicks();
  const chosen=d.dialogs().at(-1);assert.notEqual(chosen,fourth);assert.equal(chosen.querySelector('textarea').value,'Newer, shared storage only.');
  assert.doesNotMatch(chosen.textContent,/Two stored copies/);assert.equal(owner.posts().length,0,'no Save or request');chosen.close();
 }finally{d.restore();}
});
// Root disposition 4ef39e14 (review bedfbf83 F2): the checked write boundary shared by every persisting mutator.
test('comment draft checked write boundary: a stale instance never replaces newer stored text, receipt or pending custody; the current instance keeps writing',async()=>{
 const {createFeedbackDraft}=await portModule();const session=memoryStore(),backup=memoryStore();
 const open=()=>createFeedbackDraft({project:'p',key:'passage-comment',initial:{text:''},storage:session,backup});
 const seed=open();seed.update({text:'Base.',request_id:'FC-1'});
 const stale=open(),live=open(),pending={request_id:'FC-1',wire:'{"x":1}',observation:'UNKNOWN'};
 live.update({text:'Live newer.',selection:{anchor:{file:'main.tex',quote:'q'}},pending});assert.equal(live.retained,true);
 const bytes=()=>[session.map.get(DRAFT_KEY),backup.map.get(DRAFT_KEY)],after=bytes();
 stale.update({text:'Stale typing.'});assert.equal(stale.retained,false);assert.ok(stale.conflict);assert.match(stale.storageError,/changed this comment draft/);
 assert.equal(stale.snapshot().text,'Stale typing.','the refused proposal stays in memory');
 stale.settle({origin_ref:{id:'AC-late'},correction:{text:'Base.'}});assert.equal(stale.retained,false);assert.deepEqual(bytes(),after,'neither a stale update nor a late settle replaced anything');
 await assert.rejects(()=>stale.retain({},{}),/changed this comment draft/);await assert.rejects(()=>stale.pendingPayload(),/changed this comment draft/);
 live.update({text:'Live newest.'});live.update({text:'Live newest, again.'});assert.equal(live.retained,true,'the current instance keeps writing');
 const reloaded=open().snapshot();assert.equal(reloaded.text,'Live newest, again.');assert.deepEqual(reloaded.pending,pending);assert.equal(reloaded.receipt,undefined);assert.deepEqual(reloaded.selection,{anchor:{file:'main.tex',quote:'q'}});
 const a=open(),b=open();a.update({text:'A1'});b.update({text:'B1'});assert.equal(b.retained,false,'interleaved: the instance behind the latest write is stale');
 a.update({text:'A2'});assert.equal(a.retained,true);assert.equal(open().snapshot().text,'A2');
});
test('comment draft explicit choice rereads the shown copies and never drops unconfirmed Save, route or policy custody',async()=>{
 const {createFeedbackDraft}=await portModule();const session=memoryStore(),backup=memoryStore(),otherTab=memoryStore();
 const open=(store=session)=>createFeedbackDraft({project:'p',key:'passage-comment',initial:{text:''},storage:store,backup});
 const base=open();base.update({text:'Base.'});
 backup.fail=true;base.update({text:'Tab A, unconfirmed Save.',pending:{request_id:'FC-A',wire:'{"a":1}',observation:'UNKNOWN'}});backup.fail=false;
 const tabB=open(otherTab);tabB.update({text:'Tab B prose.'});
 let draft=open();assert.deepEqual(draft.disagreement.map(item=>item.store),['session','backup']);
 assert.match(draft.canChoose(1),/unconfirmed/);assert.throws(()=>draft.choose(1),/unconfirmed/);assert.equal(draft.canChoose(0),'');
 const shown=open();session.map.set(DRAFT_KEY,session.map.get(DRAFT_KEY).replace('Tab A, unconfirmed Save.','Tab A, changed after display.'));
 assert.throws(()=>shown.choose(0),/changed after they were shown/);assert.match(session.map.get(DRAFT_KEY),/changed after display/,'the unseen change is not replaced');
 draft=open();assert.equal(draft.choose(0),true);const kept=open().snapshot();assert.equal(kept.text,'Tab A, changed after display.');
 assert.deepEqual(kept.pending,{request_id:'FC-A',wire:'{"a":1}',observation:'UNKNOWN'},'the unconfirmed Save stays with its exact wire for the owner lookup');
 const legacy=state=>JSON.stringify({schema_version:'laplace.feedback-route-draft/1',project:'p',key:'passage-comment',state});
 session.map.set(DRAFT_KEY,legacy({text:'Policy copy.',policy_pending:{request_id:'FR-1'}}));backup.map.set(DRAFT_KEY,legacy({text:'Prose only.'}));
 draft=open();assert.match(draft.canChoose(1),/unconfirmed/,'a review policy request is protected too');assert.throws(()=>draft.choose(1),/unconfirmed/);assert.equal(draft.canChoose(0),'');
});
test('comment late Save reply from a closed editor cannot overwrite newer text typed after reopening; reload keeps it and one Save is reconciled by lookup',{skip:!vector},async()=>{
 const d=environment();try{
  const calls=[];let release=null;
  const request=async(path,payload)=>{calls.push({path:String(path),payload});
   if(path==='/authoring/correction-prepare')return echoed(payload);
   if(path==='/authoring/correction')return new Promise(done=>{release=()=>done(withRead(saved(payload)));});
   if(String(path).startsWith('/authoring/correction-request?')){const post=calls.find(c=>c.path==='/authoring/correction');return {...vector.lookup,request_id:post.payload.request_id,receipt:withRead(saved(post.payload))};}
   throw Error('UNRECORDED '+path);};
  const first=await openFeedbackComment({project:'p',selection:selection(),request});await settleTicks();
  const input=first.querySelector('textarea');input.value='Original instruction.';input.oninput();
  findButton(first,'Save comment').click();await settleTicks();assert.ok(release,'the Save request is in flight');first.close();
  const second=await openFeedbackComment({project:'p',selection:selection(),request});await settleTicks();
  assert.match(second.textContent,/unconfirmed/);const box=second.querySelector('textarea');box.value='Newer text typed after reopening.';box.oninput();second.close();
  release();await settleTicks();
  const reloaded=await openFeedbackComment({project:'p',selection:selection(),request});await settleTicks();
  assert.equal(reloaded.querySelector('textarea').value,'Newer text typed after reopening.','the late reply did not overwrite the newer text');
  assert.ok(!findButton(reloaded,'Check save').hidden,'the original request stays unconfirmed and checkable');
  await findButton(reloaded,'Check save').click();await settleTicks();
  assert.equal(calls.filter(c=>c.path==='/authoring/correction').length,1,'exactly one Save');
  assert.equal(calls.find(c=>c.path==='/authoring/correction').payload.text,'Original instruction.','the original request is unchanged');
  assert.match(reloaded.textContent,/Original comment saved/);assert.equal(reloaded.querySelector('textarea').value,'Newer text typed after reopening.');reloaded.close();
 }finally{d.restore();}
});
test('comment editor whose draft changed in another editor keeps its text visible, refuses to retain or send it and offers the stored draft',{skip:!vector},async()=>{
 const d=environment();try{
  const owner=recoveryOwner({refuseA:false});
  const x=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  const y=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  const yb=y.querySelector('textarea');yb.value='Typed in the other editor.';yb.oninput();
  const xb=x.querySelector('textarea');xb.value='Typed in the stale editor.';xb.oninput();
  assert.match(x.textContent,/changed in another editor/);assert.ok(x.textContent.includes('Typed in the stale editor.'),'the refused text stays visible');assert.ok(x.textContent.includes('Typed in the other editor.'));
  assert.equal(findButton(x,'Save comment').disabled,true);assert.equal(owner.posts().length,0);x.close();y.close();
  const reread=await openFeedbackComment({project:'p',selection:selection(),request:owner.request});await settleTicks();
  assert.equal(reread.querySelector('textarea').value,'Typed in the other editor.');reread.close();
 }finally{d.restore();}
});
// Root binding c60f0a37 (HOLD 3270 F1-F3): one both-copy original-request recovery protocol.
const envelope=(state,revision=null,prior=[])=>JSON.stringify({schema_version:'laplace.feedback-route-draft/1',project:'p',key:'passage-comment',...(revision?{revision}:{}),prior,state});
const heldLookup={http:{method:'GET',url:'/authoring/correction-request?project=p&request_id=x&ledger=l'}};
test('both-copy inventory dedups only the exact immutable request identity, conserves distinct wires and lets same-wire variants choose prose',async()=>{
 const port=await portModule();const session=memoryStore(),backup=memoryStore();
 const open=()=>port.createFeedbackDraft({project:'p',key:'passage-comment',initial:{text:''},storage:session,backup});
 const a=await port.retainFeedbackSubmission({project:'p',request_id:'FC-A',text:'A',source_basis:{ledger:'p/f.jsonl'}},heldLookup),b=await port.retainFeedbackSubmission({project:'p',request_id:'FC-B',text:'B',source_basis:{ledger:'p/f.jsonl'}},heldLookup);
 const policy=await port.retainFeedbackSubmission({project:'p',action:'policy-save',work_id:'W',request_id:'FP-request-1',policy:{mode:'manual'}},heldLookup);
 session.map.set(DRAFT_KEY,envelope({text:'Copy one.',pending:{...a,observation:'UNKNOWN'}}));
 backup.map.set(DRAFT_KEY,envelope({text:'Copy two.',pending:{...a,observation:'NONE',settle:{http:{method:'POST',url:'/authoring/correction-settle'}}}}));
 let draft=open(),rows=draft.inventory();
 assert.equal(rows.length,1,'the same wire at another observation is one request');assert.equal(rows[0].holders.length,2);
 assert.deepEqual(JSON.parse(rows[0].identity),['origin','p','p/f.jsonl','FC-A',a.wire_sha256]);
 assert.equal(draft.canChoose(0),'');assert.equal(draft.canChoose(1),'','either prose may be chosen while the exact wire stays');
 assert.equal(draft.choose(1),true);assert.equal(open().snapshot().pending.wire,a.wire,'the exact wire is retained after the choice');
 session.map.set(DRAFT_KEY,envelope({text:'Copy one.',pending:{...a,observation:'UNKNOWN'}}));backup.map.set(DRAFT_KEY,envelope({text:'Copy two.',pending:b,policy_pending:policy}));
 draft=open();rows=draft.inventory();
 assert.deepEqual(rows.map(r=>[r.kind,r.request_id,r.holders.map(h=>h.store+':'+h.slot)]),[['origin','FC-A',['session:pending']],['origin','FC-B',['backup:pending']],['policy','FP-request-1',['backup:policy_pending']]]);
 assert.match(draft.canChoose(0),/unconfirmed/);assert.match(draft.canChoose(1),/unconfirmed/,'distinct unresolved wires never disappear through a choice');
 backup.map.set(DRAFT_KEY,envelope({text:'Copy two.',pending:{...a,wire_sha256:'sha256:'+'0'.repeat(64)}}));
 draft=open();assert.equal(draft.inventory().length,2,'another declared wire hash is another request, never merged');assert.match(draft.canChoose(1),/unconfirmed/);
});
test('a matched per-copy outcome commits only under both shown raw copies and the exact identity, changing only that slot',async()=>{
 const port=await portModule();const session=memoryStore(),backup=memoryStore();
 const open=()=>port.createFeedbackDraft({project:'p',key:'passage-comment',initial:{text:''},storage:session,backup});
 const a=await port.retainFeedbackSubmission({project:'p',request_id:'FC-A',text:'A',source_basis:{ledger:'p/f.jsonl'}},heldLookup),b=await port.retainFeedbackSubmission({project:'p',request_id:'FC-B',text:'B',source_basis:{ledger:'p/f.jsonl'}},heldLookup);
 session.map.set(DRAFT_KEY,envelope({text:'Copy one.',unsaved_text:'kept one',selection:{anchor:{file:'main.tex'}},pending:a}));backup.map.set(DRAFT_KEY,envelope({text:'Copy two.',pending:b}));
 let draft=open();const [rowA,rowB]=draft.inventory(),shown=draft.disagreement.map(item=>({store:item.store,raw:item.raw}));
 assert.throws(()=>draft.settleCopy({index:0,slot:'pending',identity:rowA.identity,wire:rowA.wire,basis:[shown[0],{...shown[1],raw:'changed'}]},{receipt:{id:'AC-A'}}),/observation only/);
 assert.throws(()=>draft.settleCopy({index:0,slot:'pending',identity:rowB.identity,wire:rowB.wire,basis:shown},{receipt:{id:'AC-A'}}),/no longer holds/);
 const otherBytes=backup.map.get(DRAFT_KEY);session.map.set(DRAFT_KEY,session.map.get(DRAFT_KEY).replace('Copy one.','Copy one, edited elsewhere.'));
 assert.throws(()=>draft.settleCopy({index:0,slot:'pending',identity:rowA.identity,wire:rowA.wire,basis:shown},{receipt:{id:'AC-A'}}),/changed after they were shown/);
 draft=open();const again=draft.disagreement.map(item=>({store:item.store,raw:item.raw}));
 assert.equal(draft.settleCopy({index:0,slot:'pending',identity:rowA.identity,wire:rowA.wire,basis:again},{receipt:{id:'AC-A'}}),true);
 const one=JSON.parse(session.map.get(DRAFT_KEY)).state;assert.equal(one.pending,null);assert.deepEqual(one.receipt,{id:'AC-A'});assert.equal(one.text,'Copy one, edited elsewhere.');
 assert.equal(one.unsaved_text,'kept one');assert.deepEqual(one.selection,{anchor:{file:'main.tex'}});assert.equal(backup.map.get(DRAFT_KEY),otherBytes,'the other copy is untouched');
 assert.equal(draft.canChoose(1),'','with A settled, choosing B conserves every unresolved request');assert.match(draft.canChoose(0),/unconfirmed/,'B stays protected');
 backup.fail=true;const rest=draft.inventory(),nowShown=draft.disagreement.map(item=>({store:item.store,raw:item.raw}));
 assert.equal(draft.settleCopy({index:1,slot:'pending',identity:rest[0].identity,wire:rest[0].wire,basis:nowShown},{receipt:{id:'AC-B'}}),false,'a failed local write after a matched owner outcome is reported');backup.fail=false;
 assert.match(draft.lastWriteError,/quota|could not record/);assert.match(draft.storageError,/disagree/,'the copy choice itself is still pending');assert.equal(JSON.parse(backup.map.get(DRAFT_KEY)).state.pending.request_id,'FC-B','its custody is kept');
});
test('a never-retained Save attempt rolls back only its own pending field, keeps digest-time edits, and failed writes leave no phantom revision',async()=>{
 const port=await portModule();const session=memoryStore(),backup=memoryStore();
 const open=()=>port.createFeedbackDraft({project:'p',key:'passage-comment',initial:{text:''},storage:session,backup});
 const draft=open();draft.update({text:'Before.'});const last=JSON.parse(session.map.get(DRAFT_KEY)).revision.id;
 session.fail=backup.fail=true;draft.update({text:'Not retained.'});session.fail=backup.fail=false;
 draft.update({text:'Retained again.'});assert.equal(JSON.parse(session.map.get(DRAFT_KEY)).prior[0],last,'the failed attempt left no phantom revision in the lineage');
 const editor=open();const attempt=editor.retain({project:'p',request_id:'FC-late-attempt',text:'x'},heldLookup);
 editor.update({selection:{anchor:{file:'typed-during-digest'}}});
 const other=open();other.update({text:'Changed in another editor.'});
 await assert.rejects(attempt,/changed this comment draft/);
 const held=editor.snapshot();assert.equal(held.pending,null,'the never-retained, never-sent attempt is no phantom request');
 assert.deepEqual(held.selection,{anchor:{file:'typed-during-digest'}},'digest-time edits are not rolled back');assert.ok(editor.conflict,'the conflict copies are available at once');
 assert.equal(JSON.parse(session.map.get(DRAFT_KEY)).state.text,'Changed in another editor.');
 const live=open();session.fail=true;const kept=await live.retain({project:'p',request_id:'FC-partial-attempt',text:'y'},heldLookup);session.fail=false;
 assert.equal(kept.request_id,'FC-partial-attempt');assert.equal(JSON.parse(backup.map.get(DRAFT_KEY)).state.pending.request_id,'FC-partial-attempt','partial retention is custody');
});
test('the actual current owner comparison template is filled only in its declared field by the exact wire; foreign or guessed templates and associations are refused',{skip:!routeVector},async()=>{
 assert.ok(recoveryVector,'the same-scratch owner producer exported the current request-recovery DTOs');
 const port=await portModule(),view=recoveryVector.origin.absent,payload=view.payload;
 const pending=await port.retainFeedbackSubmission(payload,view.lookup);
 const template=view.legacy.compare;   // the actual current owner DTO; the negatives below are handcrafted variants of it
 const url=new URL(await port.feedbackComparisonURL(pending,template),'http://local');
 assert.equal(url.searchParams.get('submission'),pending.wire);assert.equal(url.searchParams.get('request_id'),payload.request_id);
 for(const bad of [{...template,kind:'route'},{...template,request_id:'FC-other-1'},{...template,project:'q'},{...template,field:'payload'},{...template,requires:[]},{...template,schema_version:'guessed'}])
  await assert.rejects(()=>port.feedbackComparisonURL(pending,bad),/did not issue a comparison/);
 const actual=view.association;assert.equal(port.feedbackAssociation(actual,pending).state,'UNRECORDED');
 assert.notEqual(actual.association.intent_sha256,pending.wire_sha256,'owner intent and raw wire hash are separate domains');
 assert.throws(()=>port.feedbackAssociation({association:{...actual.association,context:'elsewhere'}},pending),/does not name this exact request/);
 assert.throws(()=>port.feedbackAssociation({association:{...actual.association,kind:'route'}},pending),/does not name this exact request/);
 assert.throws(()=>port.feedbackAssociation(recoveryVector.origin.recorded.association,pending),/does not name this exact request/,'another request association never stands for this one');
});
test('opened editor with ACTUAL current owner DTOs: per-copy Checks of a recorded Save, a recorded policy and an unrecorded Save are pure, commit only matched slots and conserve the unresolved request',{skip:!routeVector},async()=>{
 assert.ok(recoveryVector,'the same-scratch owner producer exported the current request-recovery DTOs');
 const d=environment();try{
  const port=await portModule(),O=recoveryVector.origin,P=recoveryVector.policy.recorded,views=[O.recorded,O.absent,P];
  const held=view=>port.retainFeedbackSubmission(view.payload,view.lookup);
  const saved=await held(O.recorded),unsent=await held(O.absent),policy=await held(P),sel={anchor:structuredClone(O.recorded.payload.anchor)};
  globalThis.sessionStorage.setItem(DRAFT_KEY,envelope({text:'Copy holding a saved request.',selection:sel,pending:saved,policy_pending:policy}));
  globalThis.localStorage.setItem(DRAFT_KEY,envelope({text:'Copy holding an unsent request.',selection:sel,pending:unsent}));
  const calls=[];const request=async(path,body)=>{calls.push({path:String(path),body});if(body!==undefined)throw Error('A Check never posts: '+path);const url=new URL(String(path),'http://local');
   if(url.pathname==='/authoring/correction-request'){const view=views.find(item=>item.payload.request_id===url.searchParams.get('request_id')),sub=url.searchParams.get('submission');
    if(sub===null)return structuredClone(view.legacy);assert.deepEqual(JSON.parse(sub),view.payload,'only the exact retained wire fills the issued field');return structuredClone(view.association);}
   if(url.pathname==='/work/delivery'){const read=JSON.parse(url.searchParams.get('request')),view=views.find(item=>item.payload.request_id===read.request_id);
    if(!Object.hasOwn(read,'submission'))return structuredClone(view.legacy);assert.deepEqual(read.submission,view.payload,'only the exact retained wire fills the issued field');return structuredClone(view.association);}
   throw Error('UNRECORDED '+path);};
  const dialog=await openFeedbackComment({project:'p',selection:sel,request});await settleTicks();
  assert.match(dialog.textContent,/Two stored copies/);assert.match(dialog.textContent,/Unconfirmed requests in these copies/);
  const keepSession='Continue with the copy from this tab\'s browser storage; the other copy is replaced',keepBackup='Continue with the copy from shared browser storage; the other copy is replaced';
  assert.equal(findButton(dialog,keepSession).disabled,true);assert.equal(findButton(dialog,keepBackup).disabled,true,'each copy holds a request the other lacks');
  const before=[globalThis.sessionStorage.getItem(DRAFT_KEY),globalThis.localStorage.getItem(DRAFT_KEY)];
  await dialog.querySelector('[data-request-check="'+O.absent.payload.request_id+'"]').click();await settleTicks();
  assert.deepEqual([globalThis.sessionStorage.getItem(DRAFT_KEY),globalThis.localStorage.getItem(DRAFT_KEY)],before,'an unrecorded association writes nothing');
  assert.match(dialog.textContent,/no record of this exact request/);assert.ok(dialog.querySelector('[data-request-settle="'+O.absent.payload.request_id+'"]'),'the actual owner settlement is offered, never run by Check');
  await dialog.querySelector('[data-request-check="'+O.recorded.payload.request_id+'"]').click();await settleTicks();
  await dialog.querySelector('[data-request-check="'+P.payload.request_id+'"]').click();await settleTicks();
  assert.ok(calls.length>=6&&calls.every(call=>call.body===undefined),'every Check was a pure GET');
  const one=JSON.parse(globalThis.sessionStorage.getItem(DRAFT_KEY)).state;
  assert.equal(one.pending,null);assert.equal(one.receipt.request_id,O.recorded.payload.request_id);assert.deepEqual(one.receipt.origin_ref,O.recorded.legacy.receipt.origin_ref);
  assert.equal(one.policy_pending,null);assert.equal(one.route_policy_id,P.legacy.policy.id);assert.equal(one.text,'Copy holding a saved request.');
  assert.equal(globalThis.localStorage.getItem(DRAFT_KEY),before[1],'the copy holding the unsent request is untouched');
  assert.equal(findButton(dialog,keepBackup).disabled,false,'continuing with the unsent copy now conserves every unresolved request');
  assert.equal(findButton(dialog,keepSession).disabled,true,'the unsent request is still never dropped');
  assert.match(dialog.textContent,/replaces the other copy's prose/);dialog.close();
 }finally{d.restore();}
});
test('actual current owner route DTOs: the issued request-json comparison carries only the exact original route wire, and recorded, unrecorded and settled associations stay scoped to it',{skip:!routeVector},async()=>{
 assert.ok(recoveryVector,'the same-scratch owner producer exported the current request-recovery DTOs');
 const port=await portModule(),R=recoveryVector.route;
 const recorded=await port.retainFeedbackSubmission(R.recorded.payload,R.recorded.lookup),absent=await port.retainFeedbackSubmission(R.absent.payload,R.absent.lookup);
 assert.equal(await port.feedbackLookupURL(recorded,'route'),R.recorded.lookup.http.url,'the legacy handle is the actual owner read');
 const url=new URL(await port.feedbackComparisonURL(recorded,R.recorded.legacy.compare),'http://local');
 assert.equal(url.pathname,'/work/delivery');assert.deepEqual(JSON.parse(url.searchParams.get('request')),{...R.recorded.legacy.compare.read.payload,submission:R.recorded.payload});
 assert.deepEqual(port.feedbackAssociation(R.recorded.association,recorded),{state:'MATCH',effect:'RECORDED',intent:R.recorded.association.association.intent_sha256});
 assert.notEqual(R.recorded.association.association.intent_sha256,recorded.wire_sha256,'owner intent and raw wire hash are separate domains');
 const receipt=await port.feedbackRouteReceipt(R.recorded.legacy,recorded,R.recorded.payload.origin);assert.equal(receipt.aggregate.route_id,R.recorded.association.route_id);
 assert.equal(port.feedbackAssociation(R.absent.association,absent).state,'UNRECORDED');assert.equal(R.absent.association.settle.permitted,true);
 assert.deepEqual(R.absent.association.settle.payload,{project:'p',action:'request-settle',work_id:R.absent.payload.work_id,request_kind:'route',request_id:R.absent.payload.request_id});
 assert.equal(R.settle_reply.settled,true);assert.equal(port.feedbackAssociation(R.settled.association,absent).state,'MATCH');assert.equal(R.settled.association.effect,'NOT_ADMITTED');
 assert.throws(()=>port.feedbackAssociation(R.recorded.association,absent),/does not name this exact request/,'one request association never stands for another');
 await assert.rejects(()=>port.feedbackComparisonURL(absent,R.recorded.legacy.compare),/did not issue a comparison/);
});
test('a first Check in an idle reopened editor after the old reply settled the stored copy shows the reason and both copies at once and sends nothing again',{skip:!vector},async()=>{
 const d=environment();try{
  const calls=[];let release=null;
  const request=async(path,payload)=>{calls.push({path:String(path),payload});
   if(path==='/authoring/correction-prepare')return echoed(payload);
   if(path==='/authoring/correction')return new Promise(done=>{release=()=>done(withRead(saved(payload)));});
   if(String(path).startsWith('/authoring/correction-request?')){const post=calls.find(c=>c.path==='/authoring/correction');return {...vector.lookup,request_id:post.payload.request_id,receipt:withRead(saved(post.payload))};}
   throw Error('UNRECORDED '+path);};
  const first=await openFeedbackComment({project:'p',selection:selection(),request});await settleTicks();
  const input=first.querySelector('textarea');input.value='Original instruction.';input.oninput();
  findButton(first,'Save comment').click();await settleTicks();assert.ok(release,'the Save request is in flight');first.close();
  const second=await openFeedbackComment({project:'p',selection:selection(),request});await settleTicks();assert.match(second.textContent,/unconfirmed/);
  release();await settleTicks();
  assert.equal(JSON.parse(globalThis.sessionStorage.getItem(DRAFT_KEY)).state.pending,null,'the old reply settled the stored copy');
  await findButton(second,'Check save').click();await settleTicks();
  assert.match(second.textContent,/could not record that locally/,'the actual reason is shown on the first click');
  assert.match(second.textContent,/changed this comment draft/);assert.match(second.textContent,/This draft changed in another editor/,'the conflict pane and stored copies are painted at once');
  assert.equal(calls.filter(c=>c.path==='/authoring/correction').length,1,'nothing is sent again');second.close();
 }finally{d.restore();}
});
// Root disposition 02b0b0ed (HOLD 2c2d F1-F3): one shared outcome validation and consumer, one-copy and disagreement alike.
const originKey=ref=>'origin:'+JSON.stringify(ref);
const storeKey=ref=>'laplace:feedback-route:'+JSON.stringify(['p',originKey(ref)]);
const originEnvelope=(ref,state,id)=>JSON.stringify({schema_version:'laplace.feedback-route-draft/1',project:'p',key:originKey(ref),revision:{id,n:1},prior:[],state});
// Fixture transport over ACTUAL owner DTO snapshots: before/after an explicit settle, keyed by the original request id.
function routeOwner(views,phase,calls){return async(path,body)=>{calls.push({path:String(path),body});const url=new URL(String(path),'http://local');
 if(url.pathname.startsWith('/work/state'))return {project:'p',tasks:[{id:'review-claim',title:'Review this claim'}],read_cut:{revision:'r1'}};
 if(url.pathname==='/work/delivery'&&body===undefined){const read=JSON.parse(url.searchParams.get('request')),view=views[read.request_id],stage=phase.settled?view.after:view.before;
  if(!Object.hasOwn(read,'submission'))return structuredClone(stage.legacy);assert.deepEqual(read.submission,stage.payload,'only the exact retained wire fills the issued field');return structuredClone(stage.association);}
 if(url.pathname==='/work/delivery'&&body?.action==='request-settle'){const view=views[body.request_id];
  assert.deepEqual(body,{...view.before.association.settle.payload,submission:view.before.payload},'the clicked Work request-settle posts the owner-issued action with the exact retained submission');
  phase.settled=true;return structuredClone(view.reply);}
 throw Error('UNRECORDED '+path);};}
test('one shared outcome validation over actual owner DTOs: only full receipts and terminals clear custody; tampered, foreign or raced replies refuse',{skip:!routeVector},async()=>{
 assert.ok(recoveryVector?.route?.partial&&recoveryVector?.policy?.settled,'the same-scratch owner producer exported the terminal DTOs');
 const port=await portModule(),R=recoveryVector.route,P=recoveryVector.policy,held=view=>port.retainFeedbackSubmission(view.payload,view.lookup);
 const absent=await held(R.absent),partial=await held(R.partial),recorded=await held(R.recorded),pAbsent=await held(P.absent),pRecorded=await held(P.recorded);
 const whole=await port.feedbackRequestOutcome(R.settled.association,R.settled.legacy,absent);
 assert.equal(whole.fields.route_terminal.settlement.outcome_scope,'request');assert.deepEqual(whole.fields.route_terminal.preserved_effects,[]);
 const scoped=await port.feedbackRequestOutcome(R.partial_settled.association,R.partial_settled.legacy,partial);
 assert.equal(scoped.fields.route_terminal.settlement.outcome_scope,'route-admission-only');assert.equal(scoped.fields.route_terminal.preserved_effects[0].kind,'work-delivery-policy');
 const unknown=await port.feedbackRequestOutcome(R.partial.association,R.partial.legacy,partial);
 assert.equal(unknown.fields,null);assert.equal(unknown.state,'UNKNOWN');assert.equal(unknown.settle.payload.action,'request-settle');assert.equal(unknown.settle.outcome_scope,'route-admission-only');
 const policyTerminal=await port.feedbackRequestOutcome(P.settled.association,P.settled.legacy,pAbsent,'policy_pending');assert.equal(policyTerminal.fields.policy_terminal.request_kind,'policy');
 const policyReceipt=await port.feedbackRequestOutcome(P.recorded.association,P.recorded.legacy,pRecorded,'policy_pending');assert.equal(policyReceipt.fields.route_policy_id,P.recorded.association.policy.id);
 const routeReceipt=await port.feedbackRequestOutcome(R.recorded.association,R.recorded.legacy,recorded);assert.equal(routeReceipt.fields.receipt.aggregate.route_id,R.recorded.association.route_id);
 const tamper=(value,change)=>{const next=structuredClone(value);change(next);return next;};
 for(const bad of [tamper(R.settled.association,x=>{x.settlement.code='OTHER';}),tamper(R.settled.association,x=>{x.terminal=false;}),tamper(R.settled.association,x=>{x.settlement.intent_sha256='sha256:'+'0'.repeat(64);}),
  tamper(R.settled.association,x=>{x.request_kind='policy';}),tamper(R.settled.association,x=>{x.preserved_effects=[{kind:'work-delivery-policy'}];})])
  await assert.rejects(()=>port.feedbackRequestOutcome(bad,R.settled.legacy,absent),/did not establish terminal|does not preserve/);
 await assert.rejects(()=>port.feedbackRequestOutcome(tamper(R.partial_settled.association,x=>{x.preserved_effects=[];}),R.partial_settled.legacy,partial),/does not preserve/,'a route-admission-only terminal must keep its policy effect');
 await assert.rejects(()=>port.feedbackRequestOutcome(tamper(P.recorded.association,x=>{x.policy.limits={...x.policy.limits,max_new_admissions:99};}),P.recorded.legacy,pRecorded,'policy_pending'),/not yet established/);
 await assert.rejects(()=>port.feedbackRequestOutcome(tamper(P.recorded.association,x=>{x.policy.project='q';}),P.recorded.legacy,pRecorded,'policy_pending'),/not yet established/);
 await assert.rejects(()=>port.feedbackRequestOutcome(tamper(P.recorded.association,x=>{delete x.policy;}),P.recorded.legacy,pRecorded,'policy_pending'),/not yet established/,'association MATCH alone is never a receipt');
 await assert.rejects(()=>port.feedbackRequestOutcome(R.recorded.association,R.absent.legacy,recorded),/does not match/,'a raced legacy reply never stands in for the receipt');
 assert.throws(()=>port.feedbackAssociation(R.settled.association,partial),/does not name this exact request/,'another request terminal never stands for this one');
});
test('one-copy route Check with actual owner DTOs consumes the settled NOT_ADMITTED terminal through the checked local commit and becomes usable again',{skip:!routeVector},async()=>{
 assert.ok(recoveryVector?.route?.settled);
 const d=environment();try{
  const port=await portModule(),R=recoveryVector.route,O=recoveryVector.origin.recorded,ref=O.legacy.receipt.origin_ref,key=storeKey(ref),sel={anchor:structuredClone(O.payload.anchor)};
  const pending=await port.retainFeedbackSubmission(R.absent.payload,R.absent.lookup),raw=originEnvelope(ref,{text:O.payload.text,selection:sel,pending},'R-one-copy');
  globalThis.sessionStorage.setItem(key,raw);globalThis.localStorage.setItem(key,raw);
  const phase={settled:true},calls=[],request=routeOwner({[R.absent.payload.request_id]:{before:R.absent,after:R.settled,reply:R.settle_reply}},phase,calls);
  const dialog=await openFeedbackComment({project:'p',selection:sel,request,existingOrigin:{origin_ref:ref,correction:structuredClone(O.legacy.receipt.correction)}});await settleTicks();
  assert.doesNotMatch(dialog.textContent,/Two stored copies/);
  await findButton(dialog,'Check review request').click();await settleTicks();
  const state=JSON.parse(globalThis.sessionStorage.getItem(key)).state;
  assert.equal(state.pending,null);assert.equal(state.route_terminal.settlement.code,'AUTHOR_SETTLED_UNADMITTED_REQUEST');assert.equal(state.text,O.payload.text);assert.deepEqual(state.selection,sel);
  assert.match(dialog.textContent,/settled as never admitted/);assert.equal(findButton(dialog,'Check review request').hidden,true,'no stale Check remains');
  assert.ok(calls.every(call=>call.body===undefined),'a Check never posts');dialog.close();
 }finally{d.restore();}
});
test('one-copy UNKNOWN partial manual policy exposes the owner route-settle action; clicking it posts the exact body, rechecks and applies the route-admission-only terminal',{skip:!routeVector},async()=>{
 assert.ok(recoveryVector?.route?.partial);
 const d=environment();try{
  const port=await portModule(),R=recoveryVector.route,O=recoveryVector.origin.recorded,ref=O.legacy.receipt.origin_ref,key=storeKey(ref),sel={anchor:structuredClone(O.payload.anchor)};
  const pending=await port.retainFeedbackSubmission(R.partial.payload,R.partial.lookup),raw=originEnvelope(ref,{text:O.payload.text,selection:sel,pending},'R-partial-one');
  globalThis.sessionStorage.setItem(key,raw);globalThis.localStorage.setItem(key,raw);
  const phase={settled:false},calls=[],request=routeOwner({[R.partial.payload.request_id]:{before:R.partial,after:R.partial_settled,reply:R.partial_settle_reply}},phase,calls);
  const dialog=await openFeedbackComment({project:'p',selection:sel,request,existingOrigin:{origin_ref:ref,correction:structuredClone(O.legacy.receipt.correction)}});await settleTicks();
  await findButton(dialog,'Check review request').click();await settleTicks();
  assert.match(dialog.textContent,/could not establish this request outcome; you can settle it/);assert.equal(JSON.parse(globalThis.sessionStorage.getItem(key)).state.pending.request_id,R.partial.payload.request_id);
  const settleButton=findButton(dialog,'Settle this review request as never admitted');assert.equal(settleButton.hidden,false,'the owner-permitted route-settle action is exposed');
  await settleButton.click();await settleTicks();
  assert.equal(phase.settled,true);assert.equal(calls.filter(call=>call.body!==undefined).length,1,'exactly one explicit owner POST');
  const state=JSON.parse(globalThis.sessionStorage.getItem(key)).state;
  assert.equal(state.pending,null);assert.equal(state.route_terminal.settlement.outcome_scope,'route-admission-only');assert.deepEqual(state.route_terminal.preserved_effects,R.partial_settled.association.preserved_effects);
  assert.match(dialog.textContent,/recorded review policy stays recorded/);dialog.close();
 }finally{d.restore();}
});
test('whole journey with actual owner DTOs: the two-copy settle succeeds but its local write fails, the author keeps the copy holding the request, and the reopened one-copy editor recovers the same canonical outcome',{skip:!routeVector},async()=>{
 assert.ok(recoveryVector?.route?.partial);
 const d=environment();try{
  const port=await portModule(),R=recoveryVector.route,O=recoveryVector.origin.recorded,ref=O.legacy.receipt.origin_ref,key=storeKey(ref),sel={anchor:structuredClone(O.payload.anchor)};
  const pending=await port.retainFeedbackSubmission(R.partial.payload,R.partial.lookup);
  globalThis.sessionStorage.setItem(key,originEnvelope(ref,{text:O.payload.text,selection:sel,pending},'R-copy-session'));
  globalThis.localStorage.setItem(key,originEnvelope(ref,{text:O.payload.text,selection:sel,unsaved_text:'Later notes from another tab.'},'R-copy-backup'));
  const phase={settled:false},calls=[],request=routeOwner({[R.partial.payload.request_id]:{before:R.partial,after:R.partial_settled,reply:R.partial_settle_reply}},phase,calls);
  const existingOrigin={origin_ref:ref,correction:structuredClone(O.legacy.receipt.correction)};
  const first=await openFeedbackComment({project:'p',selection:sel,request,existingOrigin});await settleTicks();
  assert.match(first.textContent,/Two stored copies/);
  await first.querySelector('[data-request-check="'+R.partial.payload.request_id+'"]').click();await settleTicks();
  assert.match(first.textContent,/cannot establish this request/);
  const tab=globalThis.sessionStorage,realSet=tab.setItem;tab.setItem=(name,value)=>{if(name===key)throw Error('storage quota exceeded');return realSet(name,value);};
  await first.querySelector('[data-request-settle="'+R.partial.payload.request_id+'"]').click();await settleTicks();
  assert.equal(phase.settled,true,'the actual owner request-settle was posted with the exact retained body');
  assert.match(first.textContent,/could not record it locally/);assert.equal(JSON.parse(tab.getItem(key)).state.pending.request_id,R.partial.payload.request_id,'the copy still holds the request');
  await findButton(first,'Continue with the copy from this tab\'s browser storage; the other copy is replaced').click();await settleTicks();
  tab.setItem=realSet;
  const second=d.dialogs().at(-1);assert.notEqual(second,first);assert.doesNotMatch(second.textContent,/Two stored copies/);
  await findButton(second,'Check review request').click();await settleTicks();
  for(const store of [globalThis.sessionStorage,globalThis.localStorage]){const state=JSON.parse(store.getItem(key)).state;
   assert.equal(state.pending,null);assert.equal(state.route_terminal.settlement.outcome_scope,'route-admission-only');
   assert.deepEqual(state.route_terminal.preserved_effects,R.partial_settled.association.preserved_effects,'the partial manual-policy effect stays recorded');}
  assert.equal(calls.filter(call=>call.body!==undefined).length,1,'exactly one owner POST, the explicit settle; no Save, retry or admission');
  assert.match(second.textContent,/settled as never admitted/);second.close();
 }finally{d.restore();}
});
// Root ed923fcf (HOLD f616 F1-F3): the one-copy POLICY settle, one shared unresolved predicate and captured-basis fences.
const btn=(host,label)=>[...host.querySelectorAll('button')].find(node=>node.textContent===label);
// The exported ACTUAL owner route preview answers the editor's own route-preview read; everything else is routeOwner.
function withPreview(base,preview){return async(path,body)=>{const url=new URL(String(path),'http://local');
 if(url.pathname==='/work/delivery'&&body===undefined){const read=JSON.parse(url.searchParams.get('request')||'{}');if(read.action==='route-preview'){assert.equal(read.work_id,preview.work.id);return structuredClone(preview);}}
 return base(path,body);};}
// One held owner reply: the call is recorded when made; release(true) delivers the owner reply, release(false) loses it
// AFTER the owner acted (a lost acknowledgement), so a settle is canonical either way.
function delayed(base,hold,calls){return async(path,body)=>{calls.push({path:String(path),body});const url=new URL(String(path),'http://local');let at=null;
 if(url.pathname==='/work/delivery'){if(body?.action==='request-settle')at='settle';else if(body===undefined){const read=JSON.parse(url.searchParams.get('request')||'{}');if(read.action==='route-status')at=Object.hasOwn(read,'submission')?'compare':hold.phase.settled?'recheck':'lookup';}}
 if(at!==hold.at||hold.release)return base(path,body);
 return new Promise((resolve,reject)=>{hold.release=ok=>base(path,body).then(value=>ok?resolve(value):reject(Error('owner reply lost (test)')),reject);});};}
const stalePolicyOwner=(P,phase,calls)=>routeOwner({[P.stale.payload.request_id]:{before:P.stale,after:P.stale_settled,reply:P.stale_settle_reply}},phase,calls);
test('one-copy POLICY with a stale original CAS exposes the owner-permitted settle beside Retry: one exact POST, a pure recheck, full validation and a checked clear of only that policy, then every control recovers',{skip:!routeVector},async()=>{
 assert.ok(recoveryVector?.policy?.stale&&recoveryVector?.preview,'the same-scratch owner producer exported the stale-CAS policy and route preview DTOs');
 const d=environment();try{
  const port=await portModule(),P=recoveryVector.policy,O=recoveryVector.origin.recorded,ref=O.legacy.receipt.origin_ref,key=storeKey(ref),sel={anchor:structuredClone(O.payload.anchor)};
  assert.notEqual(P.stale.payload.expected_work_revision,P.stale_current_revision,'the retained policy CAS is stale: its exact Retry cannot be admitted');
  assert.equal(recoveryVector.preview.actions.compose.route_spec.action,'route-submit','the actual owner route wire names its kind, from which the editor derives it');
  const policyPending=await port.retainFeedbackSubmission(P.stale.payload,P.stale.lookup);
  const raw=originEnvelope(ref,{text:O.payload.text,selection:sel,route_work:recoveryVector.preview.work.id,route_preview:structuredClone(recoveryVector.preview),policy_pending:policyPending},'R-policy-one');
  globalThis.sessionStorage.setItem(key,raw);globalThis.localStorage.setItem(key,raw);
  const phase={settled:false},calls=[],request=withPreview(stalePolicyOwner(P,phase,calls),recoveryVector.preview);
  const dialog=await openFeedbackComment({project:'p',selection:sel,request,existingOrigin:{origin_ref:ref,correction:structuredClone(O.legacy.receipt.correction)},readerPlace:{routeOpen:true}});await settleTicks();
  const send=btn(dialog,'Request reviews');assert.equal(send.disabled,true,'a held policy request disables Request reviews');
  assert.equal(btn(dialog,'Save automatic review settings').disabled,true,'and a new automatic policy');
  const quiet=calls.length;
  for(const handler of [send.onclick,btn(dialog,'Save comment').onclick,btn(dialog,'Save automatic review settings').onclick]){await handler();assert.match(dialog.textContent,/still unconfirmed\. Check or settle it first/,'a programmatic handler refuses through the same predicate');}
  assert.equal(calls.length,quiet,'no refused handler made any request');
  await btn(dialog,'Check policy submission').click();await settleTicks();
  assert.match(dialog.textContent,/Policy submission none/);assert.ok(btn(dialog,'Retry this exact policy submission'),'the exact retry stays available');
  const settleButton=btn(dialog,'Settle this review policy request as never admitted');assert.ok(settleButton,'Retry is not the only escape: the owner-permitted settle is exposed');
  assert.ok(calls.every(call=>call.body===undefined),'the Check is pure');
  await settleButton.click();await settleTicks();
  const posts=calls.filter(call=>call.body!==undefined);assert.equal(posts.length,1,'exactly one owner POST');assert.deepEqual(posts[0].body,{...P.stale.association.settle.payload,submission:P.stale.payload});
  const after=calls.slice(calls.indexOf(posts[0])+1).map(call=>new URL(call.path,'http://local')).filter(url=>url.pathname==='/work/delivery').map(url=>JSON.parse(url.searchParams.get('request')));
  assert.ok(after.some(read=>!Object.hasOwn(read,'submission'))&&after.some(read=>Object.hasOwn(read,'submission')),'the recheck is the issued lookup and pure comparison');
  for(const store of [globalThis.sessionStorage,globalThis.localStorage]){const state=JSON.parse(store.getItem(key)).state;
   assert.equal(state.policy_pending,null);assert.deepEqual(state.policy_terminal,P.stale_settled.association,'the full validated owner terminal is recorded');
   assert.equal(state.text,O.payload.text);assert.deepEqual(state.selection,sel);assert.equal(state.route_work,recoveryVector.preview.work.id);assert.ok(state.route_preview,'the inspected preview is kept');}
  assert.match(dialog.textContent,/review policy request was settled as never admitted/);assert.equal(btn(dialog,'Check policy submission'),undefined,'no stale policy Check remains');
  assert.equal(send.disabled,false,'Request reviews recovers');assert.equal(btn(dialog,'Save automatic review settings').disabled,false,'a new automatic policy is possible again');
  dialog.close();
 }finally{d.restore();}
});
test('a one-copy policy settle the owner records but this editor cannot write keeps custody and the other slot; the reopened editor pure Check recovers the same terminal with no second POST',{skip:!routeVector},async()=>{
 assert.ok(recoveryVector?.policy?.stale);
 const d=environment();try{
  const port=await portModule(),P=recoveryVector.policy,R=recoveryVector.route,O=recoveryVector.origin.recorded,ref=O.legacy.receipt.origin_ref,key=storeKey(ref),sel={anchor:structuredClone(O.payload.anchor)};
  const policyPending=await port.retainFeedbackSubmission(P.stale.payload,P.stale.lookup),routePending=await port.retainFeedbackSubmission(R.absent.payload,R.absent.lookup);
  const raw=originEnvelope(ref,{text:O.payload.text,selection:sel,pending:routePending,policy_pending:policyPending},'R-policy-local-fail');
  globalThis.sessionStorage.setItem(key,raw);globalThis.localStorage.setItem(key,raw);
  const phase={settled:false},calls=[],request=stalePolicyOwner(P,phase,calls);
  const args={project:'p',selection:sel,request,existingOrigin:{origin_ref:ref,correction:structuredClone(O.legacy.receipt.correction)}};
  const first=await openFeedbackComment(args);await settleTicks();
  assert.ok(btn(first,'Check review request'),'the other held request keeps its own Check');
  await btn(first,'Check policy submission').click();await settleTicks();
  const stores=[globalThis.sessionStorage,globalThis.localStorage],kept=stores.map(store=>store.getItem(key)),real=stores.map(store=>store.setItem);
  for(const store of stores){const set=store.setItem;store.setItem=(name,value)=>{if(name===key)throw Error('storage quota exceeded');return set(name,value);};}
  await btn(first,'Settle this review policy request as never admitted').click();await settleTicks();
  assert.equal(phase.settled,true,'the owner recorded the settlement');assert.match(first.textContent,/could not record that locally/);
  assert.deepEqual(stores.map(store=>store.getItem(key)),kept,'custody is kept exactly');
  stores.forEach((store,i)=>{store.setItem=real[i];});first.close();
  const second=await openFeedbackComment(args);await settleTicks();
  assert.ok(btn(second,'Check policy submission'),'the reopened one-copy editor still holds the policy request');
  await btn(second,'Check policy submission').click();await settleTicks();
  for(const store of stores){const state=JSON.parse(store.getItem(key)).state;
   assert.equal(state.policy_pending,null);assert.deepEqual(state.policy_terminal,P.stale_settled.association);
   assert.equal(state.pending.wire,routePending.wire,'the other pending slot is preserved');assert.equal(state.text,O.payload.text);}
  assert.equal(calls.filter(call=>call.body!==undefined).length,1,'one owner POST in all: no resubmit, retry or paid effect');
  assert.match(second.textContent,/settled as never admitted/);second.close();
 }finally{d.restore();}
});
test('fresh editor: a held policy request disables Save and refuses a programmatic Save before any wire; after its checked settle Save is available again',{skip:!routeVector||!vector},async()=>{
 const d=environment();try{
  const port=await portModule(),P=recoveryVector.policy,policyPending=await port.retainFeedbackSubmission(P.stale.payload,P.stale.lookup);
  const raw=envelope({text:'Kept prose for a new comment.',selection:selection(),policy_pending:policyPending},{id:'R-fresh-policy',n:1});
  globalThis.sessionStorage.setItem(DRAFT_KEY,raw);globalThis.localStorage.setItem(DRAFT_KEY,raw);
  const phase={settled:false},calls=[],owner=stalePolicyOwner(P,phase,calls),request=async(path,body)=>path==='/authoring/correction-prepare'?prepared(body):owner(path,body);
  const dialog=await openFeedbackComment({project:'p',selection:selection(),request});await settleTicks();
  const save=btn(dialog,'Save comment');assert.equal(save.disabled,true,'a held policy request disables Save');
  await save.onclick();assert.match(dialog.textContent,/still unconfirmed\. Check or settle it first/);
  assert.ok(calls.every(call=>!String(call.path).startsWith('/authoring/correction')),'a programmatic Save sends nothing');
  await btn(dialog,'Check policy submission').click();await settleTicks();
  await btn(dialog,'Settle this review policy request as never admitted').click();await settleTicks();
  const state=JSON.parse(globalThis.sessionStorage.getItem(DRAFT_KEY)).state;
  assert.equal(state.policy_pending,null);assert.equal(state.policy_terminal.request_id,P.stale.payload.request_id);assert.equal(state.text,'Kept prose for a new comment.');
  assert.equal(save.disabled,false,'Save is available again once no request is unresolved');
  assert.equal(calls.filter(call=>call.body!==undefined).length,1);dialog.close();
 }finally{d.restore();}
});
test('one-copy delayed compare, settle and recheck, delivered or lost, across Close, a new view, a same-ID changed wire and unsent typing: the basis captured before the first await holds',{skip:!routeVector||!vector},async()=>{
 const port=await portModule(),P=recoveryVector.policy,id=P.stale.payload.request_id;
 const changedPayload={...P.stale.payload,policy:{...P.stale.payload.policy,limits:{...P.stale.payload.policy.limits,max_new_admissions:1}}};
 for(const at of ['compare','settle','recheck'])for(const delivered of [true,false])for(const change of ['close','view','wire','typing']){const label=at+'/'+(delivered?'reply':'lost')+'/'+change;
  const d=environment();try{
   const held=await port.retainFeedbackSubmission(P.stale.payload,P.stale.lookup),changed=await port.retainFeedbackSubmission(changedPayload,P.stale.lookup);
   const seed=envelope({text:'Kept prose.',selection:selection(),policy_pending:held},{id:'R-late',n:1});globalThis.sessionStorage.setItem(DRAFT_KEY,seed);globalThis.localStorage.setItem(DRAFT_KEY,seed);
   const phase={settled:at==='compare'},hold={at,phase,release:null},calls=[],owner=delayed(stalePolicyOwner(P,phase,[]),hold,calls);
   const request=async(path,body)=>path==='/authoring/correction-prepare'?prepared(body):owner(path,body);
   const args={project:'p',selection:selection(),request};let dialog=await openFeedbackComment(args);await settleTicks();
   if(at==='compare')btn(dialog,'Check policy submission').click();
   else{await btn(dialog,'Check policy submission').click();await settleTicks();btn(dialog,'Settle this review policy request as never admitted').click();}
   for(let i=0;i<40&&!hold.release;i++)await settleTicks();assert.ok(hold.release,label+': the owner reply is held');
   const mark=calls.length,old=dialog;
   if(change==='close')dialog.close();
   if(change==='view'){dialog.close();dialog=await openFeedbackComment(args);await settleTicks();}
   if(change==='wire'){const moved=envelope({text:'Kept prose.',selection:selection(),policy_pending:changed},{id:'R-other',n:2},['R-late']);globalThis.sessionStorage.setItem(DRAFT_KEY,moved);globalThis.localStorage.setItem(DRAFT_KEY,moved);}
   if(change==='typing'){const t=dialog.querySelector('textarea');t.value='Typed while the reply was held.';t.oninput();}
   hold.release(delivered);await settleTicks();await settleTicks();
   assert.equal(calls.slice(mark).filter(call=>new URL(call.path,'http://local').pathname==='/work/delivery').length,0,label+': no lookup, POST or recheck after the basis moved');
   for(const store of [globalThis.sessionStorage,globalThis.localStorage]){const state=JSON.parse(store.getItem(DRAFT_KEY)).state;
    assert.equal(state.policy_terminal,undefined,label+': the old outcome is never adopted');assert.equal(state.policy_pending.wire,change==='wire'?changed.wire:held.wire,label+': custody is never cleared');
    assert.equal(state.text,change==='typing'?'Typed while the reply was held.':'Kept prose.',label+': prose is never overwritten');}
   assert.doesNotMatch(old.textContent,/settled as never admitted/,label+': no old outcome is painted');
   if(change==='view')assert.doesNotMatch(dialog.textContent,/settled as never admitted|owner reply lost/,label+': the new view is not repainted by the old reply');
   assert.equal(phase.settled,true,label+': the owner outcome is canonical');
   if(change==='view'||change==='typing'){await btn(dialog,'Check policy submission').click();await settleTicks();
    const state=JSON.parse(globalThis.sessionStorage.getItem(DRAFT_KEY)).state;assert.equal(state.policy_pending,null,label+': a fresh Check adopts the canonical outcome');
    assert.deepEqual(state.policy_terminal,P.stale_settled.association);assert.equal(state.text,change==='typing'?'Typed while the reply was held.':'Kept prose.');}
   if(dialog.isConnected!==false)dialog.close();
  }finally{d.restore();}}
});
test('two-copy delayed compare and settle, delivered or lost, across Close, a copy choice made in another editor and a same-ID changed wire: the shown-and-stored basis captured before the first await holds',{skip:!routeVector||!vector},async()=>{
 const port=await portModule(),P=recoveryVector.policy,id=P.stale.payload.request_id;
 const changedPayload={...P.stale.payload,policy:{...P.stale.payload.policy,limits:{...P.stale.payload.policy.limits,max_new_admissions:1}}};
 for(const at of ['compare','settle'])for(const delivered of [true,false])for(const change of ['close','choice','wire']){const label='two-copy '+at+'/'+(delivered?'reply':'lost')+'/'+change;
  const d=environment();try{
   const held=await port.retainFeedbackSubmission(P.stale.payload,P.stale.lookup),changed=await port.retainFeedbackSubmission(changedPayload,P.stale.lookup);
   globalThis.sessionStorage.setItem(DRAFT_KEY,envelope({text:'Copy one.',selection:selection(),policy_pending:held}));globalThis.localStorage.setItem(DRAFT_KEY,envelope({text:'Copy two.',selection:selection()}));
   const phase={settled:at==='compare'},hold={at,phase,release:null},calls=[],request=delayed(stalePolicyOwner(P,phase,[]),hold,calls);
   const dialog=await openFeedbackComment({project:'p',selection:selection(),request});await settleTicks();assert.match(dialog.textContent,/Two stored copies/);
   const check=()=>dialog.querySelector('[data-request-check="'+id+'"]');
   if(at==='compare')check().click();
   else{await check().click();await settleTicks();dialog.querySelector('[data-request-settle="'+id+'"]').click();}
   for(let i=0;i<40&&!hold.release;i++)await settleTicks();assert.ok(hold.release,label+': the owner reply is held');
   const mark=calls.length;
   if(change==='close')dialog.close();
   if(change==='choice'){const other=port.createFeedbackDraft({project:'p',key:'passage-comment',initial:{text:''},storage:globalThis.sessionStorage,backup:globalThis.localStorage});assert.equal(other.choose(0),true,label+': another editor chose the copy holding the request');}
   if(change==='wire')globalThis.sessionStorage.setItem(DRAFT_KEY,envelope({text:'Copy one.',selection:selection(),policy_pending:changed}));
   hold.release(delivered);await settleTicks();await settleTicks();
   assert.equal(calls.slice(mark).filter(call=>new URL(call.path,'http://local').pathname==='/work/delivery').length,0,label+': no lookup, POST or recheck after the basis moved');
   const states=[globalThis.sessionStorage,globalThis.localStorage].map(store=>JSON.parse(store.getItem(DRAFT_KEY)).state);
   assert.ok(states.every(state=>state.policy_terminal===undefined),label+': the old outcome is never adopted');
   assert.equal(states[0].policy_pending.wire,change==='wire'?changed.wire:held.wire,label+': the copy keeps its request');
   if(change==='choice')assert.equal(states[1].policy_pending.wire,held.wire,label+': the chosen copy keeps the request');
   assert.doesNotMatch(dialog.textContent,/now records that outcome/,label+': no old outcome is painted');assert.equal(phase.settled,true,label+': the owner outcome is canonical');
   if(dialog.isConnected!==false)dialog.close();
  }finally{d.restore();}}
});
test('late metadata preparation cannot update a closed comment editor',{skip:!vector},async()=>{
 const d=environment();try{let resolve;const opened=openFeedbackComment({project:'p',selection:selection(),request:async(_path,payload)=>new Promise(done=>resolve=()=>done(prepared(payload)))});while(!resolve)await new Promise(done=>setTimeout(done,0));const dialog=d.dialogs().at(-1);dialog.close();resolve();await opened;assert.equal(d.dialogs().length,0);assert.equal(d.body.textContent.includes('Original passage inspected'),false);
 }finally{d.restore();}
});
