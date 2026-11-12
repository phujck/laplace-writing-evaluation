import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {mountOperatorWork} from '../src/laplace/web/static_shared/workspace-work.mjs';
import {workSelectionFixture,workDetail} from './helpers/work_selection_harness.mjs';
const mixed=JSON.parse(readFileSync(new URL('./fixtures/work-reader-state/mixed-renewal.json',import.meta.url),'utf8'));
const copy=value=>structuredClone(value);
const visibleText=node=>node.hidden?'':node._text+(node.tag==='details'&&!node.open?node.children.filter(n=>n.tag==='summary'):node.children).map(visibleText).join(' ');
const question={id:'assumptions',label:'Which assumptions make the claim valid?',scope:'other',required:true,status:'AWAITING_REVIEW',satisfied:false,currentness:'UNKNOWN',inputs_total:1};
const detail=()=>({project:'p',view:'detail',read_cut:{revision:'cut'},task:{id:'review-claim',title:'Review the numerical claim',goal:'Check the selected claim. α 中 🌱.\n\nKeep the exact full second paragraph; do not infer its summary.',summary:'Recorded earlier summary.',status:'open',recorded_status:'open',lifecycle:{status:'open',closed:false,completed:false},readiness:{status:'READY',reason:'Declared prerequisites met.'},current_acceptance:{status:'NOT_REQUIRED',review_required:false,reason:'Task is not complete.'},standing:{group:'awaiting',facts:[{code:'awaiting-review',text:'Awaiting review'}]},activity:{state:null,qualification:'No in-app or attested external execution observed.',coverage:{partial:false}},review:{managed:true,obligations:[copy(question)],remaining:['assumptions'],reviews_recorded:0,pending_joins:[],next:{kind:'review',says:'Inspect the review before deciding.'}},deliveries:{recipients:[copy(mixed.current)],recipients_total:2,events:[copy(mixed.event)],events_total:3}},blockers:[],allowed_actions:{},acceptance:{goal:null,mechanical:['Current prerequisite standing','Exact consumed scope and completion evidence'],scientific_verification:false},children:{items:[]},dependants:{items:[]},requires:{items:[]}});
async function mount(value,options={}){const dom=installDOM(),host=new Node('main');dom.body.append(host);const calls=[];const controller=await mountOperatorWork(host,{project:'p',summary:{tasks:[value.task]},initialWork:value.task.id,request:async(path,payload)=>{calls.push({path,payload});assert.equal(payload,undefined,'presentation never posts');return copy(value);},...options});return {dom,host,controller,calls,restore(){controller.destroy();dom.restore();}};}

test('Work purpose and one owner standing lead; exact long brief, status and machinery remain optional',async()=>{
 const value=detail(),s=await mount(value);try{
  const header=s.host.querySelector('.operator-work-heading'),visible=visibleText(header);
  assert.ok(visible.indexOf('Check the selected claim. α 中 🌱.')<visible.indexOf('Awaiting review'));
  assert.equal(header.querySelectorAll('.state-chip').length,1);
  assert.equal(header.querySelector('.operator-work-brief').querySelector('p').textContent,value.task.goal);
  assert.ok(!visible.includes('second paragraph')&&!visible.includes('Recorded earlier summary'));
  const content=visibleText(s.host);assert.ok(!content.includes('Current prerequisite standing')&&!content.includes('scientific verification'));
  assert.equal(s.host.querySelector('.operator-acceptance').tag,'details');assert.equal(s.host.querySelector('.operator-acceptance').open,undefined);
  assert.equal(s.host.querySelector('.operator-work-facets').children[0].textContent,'Status details');
  assert.match(s.host.textContent,/Declared prerequisites met/);assert.match(s.host.textContent,/Task is not complete/);
  assert.equal(s.calls.length,1);
 }finally{s.restore();}
});

test('Actual mixed response/activity/review and original versus renewed approvals stay distinct',async()=>{
 const turns=[],s=await mount(detail(),{onTurn:async(...args)=>turns.push(args)});try{
  const content=visibleText(s.host),event=s.host.querySelector('.work-delivery-event');
  assert.match(content,/Response available/);assert.match(content,/Execution is still reported active/);assert.match(content,/Review decision pending/);assert.match(content,/Decision currentness is unknown/);
  assert.match(content,/1 of 2 saved reviewer settings shown/);assert.match(content,/1 of 3 review requests shown/);assert.ok(!content.includes(mixed.event.id)&&!content.includes(mixed.current.id));
  assert.equal(event.querySelector('h5').textContent,mixed.event.recipient.label);assert.match(content,/Effort: low/);
  assert.notEqual(mixed.event.recipient.revision,mixed.current.revision);assert.ok(event.querySelector('pre').textContent.includes(mixed.event.recipient.revision));assert.ok(!event.querySelector('pre').textContent.includes(mixed.current.revision));
  await findButton(s.host,'Read review turn').onclick();assert.deepEqual(turns,[[mixed.event.admitted.turn_id,{sessionId:mixed.event.admitted.session_id}]]);
  assert.match(content,/0 of 1 required review obligations satisfied/);assert.ok(!/Completed/.test(visibleText(event)));
 }finally{s.restore();}
});

test('Concrete blocker and stale acceptance stay visible, and partial waiting is not promoted to completion',async()=>{
 const value=detail();value.task.lifecycle={status:'done',closed:true,completed:true};value.task.current_acceptance={status:'STALE',review_required:true,reason:'Selected source changed.'};value.task.standing={group:'attention',facts:[{code:'done-stale',text:'Done; acceptance stale'}]};value.task.activity={state:'waiting',qualification:'In-app waiting, observed now',coverage:{in_app:{owner:'writing.turn_jobs',rows:1,omitted:2,untargeted:0,covers:'accepted turn starts, live turns and child hosts that name a Work',not_covered:'research runs and turns admitted without a Work target'},external:{owner:'project-work-observation rows (human attestation door)',works:0,rows:0},partial:true}};value.blockers=[{sentence:'Waiting on the revised boundary check.',consumed_revision:'old',observed_revision:'new',subject:{owner:'literature'},next_actions:[],read_handles:[]}];
 const s=await mount(value);try{const content=visibleText(s.host);assert.match(content,/Done; acceptance stale/);assert.match(content,/Waiting on the revised boundary check/);assert.match(content,/In-app waiting, observed now.*coverage partial/);assert.ok(!content.includes('Consumed: old'));assert.match(s.host.textContent,/Consumed: old/);}finally{s.restore();}
});

test('Background progress preserves dirty form, original guard, focus and a later explicit navigation',async()=>{
 const f=await workSelectionFixture();try{
  const form=f.host.all().find(n=>n.tag==='form'),input=form.querySelector('textarea');input.value='UNSENT EXACT EVIDENCE α';form.oninput();input.focus();const original=copy(f.controller.capture().drafts.B.completionBasis);
  let release;f.setRead(()=>new Promise(resolve=>{release=()=>{const value=workDetail('fixture','B','in-progress');value.task.activity={state:'running',qualification:'In-app running, observed now',observations:[{source:'in-app',subject:{kind:'session',turn_id:'WT-observed'},observed_state:'running',current:true}],subjects_total:1,coverage:{partial:false}};resolve(value);};}));
  const refresh=f.owner.refreshSelectedWork({project:'fixture',work_id:'B',turn_id:'T',session_id:'S'},()=>true);
  const other=new Node('button');document.body.append(other);other.focus();release();await refresh;
  assert.equal(f.host.all().find(n=>n.tag==='form'),form);assert.equal(input.value,'UNSENT EXACT EVIDENCE α');assert.deepEqual(f.controller.capture().drafts.B.completionBasis,original);assert.equal(document.activeElement,other);assert.match(f.host.querySelector('.operator-work-heading').textContent,/in-progress/);assert.match(f.host.querySelector('.work-activity').textContent,/In-app running, observed now/);
  let finish;f.setRead(url=>url.includes('id=B')?new Promise(resolve=>{finish=()=>resolve(workDetail('fixture','B','done'));}):f.readDefault(url));
  const late=f.owner.refreshSelectedWork({project:'fixture',work_id:'B',turn_id:'T',session_id:'S'},()=>true);await f.owner.requestWorkSelection('C');finish();await late;assert.equal(f.controller.detail.task.id,'C');assert.equal(f.owner.currentTask().id,'C');
 }finally{f.restore();}
});


function handoffDetail(){const value=detail();value.task.review.next={kind:'handoff',says:'Submit the implementation for scoped review (metadata only; nothing is launched).'};value.allowed_actions.work_review={permitted:true,phases:['handoff','review'],payload:{id:'review-claim',expected_work_revision:'old'},http:{method:'POST',url:'/work/review'},preparation:{initial:'handoff',phases:{handoff:{title:'Record handoff',basis:{expected_work_revision:'old'},inputs:[{name:'summary',path:'summary',label:'Work to be reviewed',input:'area'}]},review:{title:'Record scoped review',basis:{expected_work_revision:'old'},inputs:[{name:'findings',path:'findings',label:'Findings',input:'findings'}]}}}};return value;}
test('Open review form navigates to the same retained draft and current parent after a background update',async()=>{
 const value=handoffDetail(),held={phase:'review',fields:{findings:'F1: HELD α'},request_id:'REQUEST-held',basis:{expected_work_revision:'old'},dirty:true},s=await mount(value,{memory:{drafts:{'review-claim':{review:copy(held),dirty:true}}}});try{
  const recorder=s.host.querySelector('.operator-review-recorder'),phase=recorder.querySelector('select'),form=recorder.querySelector('form');recorder.open=false;
  assert.match(visibleText(s.host),/Describe the work to be reviewed, then record its handoff/);assert.ok(!visibleText(s.host).includes('metadata only'));assert.ok(s.host.textContent.includes(value.task.review.next.says));
  const before=copy(s.controller.capture().drafts['review-claim'].review),control=findButton(s.host,'Open review form');
  await control.onclick();assert.equal(recorder.open,true);assert.equal(document.activeElement,phase);assert.equal(phase.value,'review');assert.equal(recorder.querySelector('form'),form);assert.deepEqual(s.controller.capture().drafts['review-claim'].review,before);assert.equal(s.calls.length,1);
  recorder.open=false;await s.controller.select('review-claim',null,{observation:true});
  assert.equal(s.host.querySelector('.operator-review-recorder'),recorder,'existing dirty recorder stays mounted');
  const current=findButton(s.host,'Open review form');assert.notEqual(current,control);await current.onclick();assert.equal(recorder.open,true);assert.equal(document.activeElement,phase);assert.equal(phase.value,'review');assert.deepEqual(s.controller.capture().drafts['review-claim'].review,before);
  s.controller.destroy();recorder.open=false;const other=new Node('button');document.body.append(other);other.focus();await current.onclick();assert.equal(recorder.open,false);assert.equal(document.activeElement,other,'stale navigation never steals later author focus');
 }finally{s.restore();}
});
test('Handoff navigation promises no unavailable/read-only form and leaves other next kinds unchanged',async()=>{
 for(const kind of ['read-only','not-permitted','missing-preparation','other-kind']){const value=handoffDetail(),options={};if(kind==='read-only')options.readOnly=true;if(kind==='not-permitted')value.allowed_actions.work_review.permitted=false;if(kind==='missing-preparation')value.allowed_actions.work_review.preparation={phases:{}};if(kind==='other-kind')value.task.review.next={kind:'synthesis',says:'Retain the exact synthesis instruction.'};const s=await mount(value,options);try{assert.equal(s.host.all().filter(n=>n.tag==='button'&&n.textContent==='Open review form').length,0,kind);if(kind==='other-kind')assert.ok(visibleText(s.host).includes('Retain the exact synthesis instruction.'));assert.equal(s.calls.length,1);}finally{s.restore();}}
});
