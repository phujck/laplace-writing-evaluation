// The Work navigator, the relationships panel, the observer loop and observation handling
// (WORK-source-state-work-review-context-20261015, Sol D2-B/D/E). The navigator and relationship tests run on
// replies produced by the REAL Work owner over a synthetic tmp root (ownerReplies below), so the painted shapes
// are the owner's, not a hand-written second contract; lifetime and focus edges use small hand fixtures.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {mountOperatorWork} from '../src/laplace/web/static_shared/workspace-work.mjs';
import {observeWork} from '../src/laplace/web/static_shared/workspace-work-observer.mjs';
import {standingChip} from '../src/laplace/web/static_shared/workspace-work-navigator.mjs';

const replies=(()=>{
 const result=spawnSync('./scripts/laplace-python',['-c',String.raw`
import json,tempfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from laplace.work import project_work as w; from laplace.web import project_work_surface as http
out={}
with tempfile.TemporaryDirectory(prefix='laplace-work-nav-owner-') as raw:
 root=Path(raw);(root/'contract').mkdir()
 def make(i,**f):w.task('p',{'id':i,'title':'Title '+i,'goal':'Goal of '+i,**f},root)
 def raw_row(i,**f):
  spec={k:v for k,v in w._tasks('p',root)[i].items() if k!='phases'};w._append(root,{**spec,**f,'record':'project-work','id':i,'task_id':i})
 make('C');make('B',parent_work_id='C')
 for n in range(9):make('T%d'%n,parent_work_id='B')
 raw_row('T1',depends_on=['T5']);raw_row('T7',depends_on=['T8']);raw_row('T8',depends_on=['T7'])
 for n in range(14):make('U%02d'%n)
 make('A',parent_work_id='C');(root/'a.txt').write_text('a')
 g=w.read('p',{'view':'detail','id':'A'},root)['allowed_actions']['task_status']['payload'];w.transition('p',{**g,'status':'done','evidence':['a.txt']},root)
 (root/'a.txt').write_text('changed after completion')
 def get(url):
  u=urlsplit(url);code,_,body=http.handle(u.path,parse_qs(u.query),'GET',repo_root=root);assert code==200,body[:300];return json.loads(body)
 def q(**v):
  from urllib.parse import urlencode;return '/work/state?'+urlencode({'project':'p',**v})
 for key,url in [('roots',q(view='roots')),('branchC',q(view='branch',id='C')),('branchB',q(view='branch',id='B',limit=6)),('detailB',q(view='detail',id='B',limit=6)),('detailT1',q(view='detail',id='T1')),('detailT0',q(view='detail',id='T0')),('detailC',q(view='detail',id='C'))]:
  out[key]={'url':url,'value':get(url)}
 out['roots2']={'url':out['roots']['value']['pagination']['next_read']['http']['url'],'value':get(out['roots']['value']['pagination']['next_read']['http']['url'])}
 out['detailB2']={'url':out['detailB']['value']['children']['next_read']['http']['url'],'value':get(out['detailB']['value']['children']['next_read']['http']['url'])}
 out['branchB2']={'url':out['branchB']['value']['pagination']['next_read']['http']['url'],'value':get(out['branchB']['value']['pagination']['next_read']['http']['url'])}
 # wave 8: the owner's group lists at the same cut as roots (every depth); Ready continues past one page, Closed is empty
 at=out['roots']['value']['read_cut']['revision']
 for group in ('attention','ready','blocked','settled','in-progress','awaiting'):
  out['group-'+group]={'url':q(view='group',group=group,as_of=at),'value':get(q(view='group',group=group,as_of=at))}
 out['group-ready2']={'url':out['group-ready']['value']['pagination']['next_read']['http']['url'],'value':get(out['group-ready']['value']['pagination']['next_read']['http']['url'])}
 parent='U13'
 for n in range(14):make('D%02d'%n,parent_work_id=parent);parent='D%02d'%n
 out['attention']={'url':q(view='attention'),'value':get(q(view='attention'))}
 out['branchD13']={'url':q(view='branch',id='D13'),'value':get(q(view='branch',id='D13'))}
 import hashlib
 from laplace.work import project_work_review as review
 (root/'src').mkdir();(root/'src'/'a.py').write_text('a = 1\n')
 make('RV',parent_work_id='U12',review_obligations=[{'id':'source','scope':'source','label':'Source review','inputs':['src/a.py']}])
 out['detailRV']={'url':q(view='detail',id='RV'),'value':get(q(view='detail',id='RV'))}
 guard=out['detailRV']['value']['allowed_actions']['work_review']['payload']['expected_work_revision']
 review.record('p',{'id':'RV','phase':'handoff','request_id':'req-handoff-ext','expected_work_revision':guard,'pins':{'src/a.py':'sha256:'+hashlib.sha256(b'a = 1\n').hexdigest()}},root,door={'origin':'human'})
 out['detailRV_after']={'url':'variant:rv-after','value':get(q(view='detail',id='RV'))}
 w.task('p',{'id':'RV','title':'Title RV renamed','expected_work_revision':w._task_revision(w._tasks('p',root)['RV'])},root)
 out['detailRV_edited']={'url':'variant:rv-edited','value':get(q(view='detail',id='RV'))}
 real=w.disposition_policy
 def strict(row,effective,repo_root=None,**kw):
  value=real(row,effective,repo_root,**kw);refused={**value['refused'],'in-progress':'This fixture owner forbids starting Work.'}
  return {**value,'refused':refused,'statuses':[x for x in value['statuses'] if x not in refused]}
 w.disposition_policy=strict
 out['detailT0_strict']={'url':'variant:t0-strict','value':get(q(view='detail',id='T0'))}
 out['agentT0_strict']={'url':'variant:agent','value':w.read('p',{'view':'detail','id':'T0'},root,mode='work')['allowed_actions']['task_status']}
 w.disposition_policy=real
print(json.dumps(out))
`],{cwd:fileURLToPath(new URL('..',import.meta.url)),encoding:'utf8',timeout:60000,env:{...process.env,LAPLACE_STATE:'/nonexistent-laplace-state-for-fixture'}});
 if(result.status!==0)throw Error(result.stderr||'The real Work owner fixture refused');return JSON.parse(result.stdout);
})();
const key=url=>{const u=new URL(url,'http://local'),p=u.searchParams;return [p.get('view'),p.get('id')||'',p.get('offset')||'0',p.get('group')||''].join('|');};
function owner(extra=null){
 const table=new Map(Object.values(replies).filter(({url})=>!url.startsWith('variant:')).map(({url,value})=>[key(url),value])),calls=[];
 return {calls,request:async(url,payload)=>{calls.push({url,payload});if(payload)throw Error('no writes in this test');if(extra){const value=await extra(url);if(value!==undefined)return structuredClone(value);}
  const p=new URL(url,'http://local').searchParams,view=p.get('view'),id=p.get('id')||'';
  const found=table.get(key(url))||(view==='detail'?replies['detail'+id]?.value:view==='branch'&&p.get('offset')==null?replies['branch'+id]?.value:null);
  if(!found)throw Error('unexpected read '+url);return structuredClone(found);}};
}
async function mount(transport,{initialWork=null}={}){
 const dom=installDOM(),host=new Node('section');dom.body.append(host);const selections=[];
 const controller=await mountOperatorWork(host,{project:'p',summary:{project:'p',view:'summary',tasks:[]},request:transport.request,initialWork,navigation:true,onSelect:task=>selections.push(task?.id||null)});
 return {dom,host,controller,selections};
}
const views=calls=>calls.map(({url})=>new URL(url,'http://local').searchParams.get('view'));

test('the navigator opens on roots: campaigns are Work with separate Inspect and Open controls and a working continuation',async()=>{
 const t=owner(),{host,controller,dom}=await mount(t);try{
  assert.deepEqual(views(t.calls),['roots']);
  const campaign=host.querySelector('[data-open-work="C"]');assert.ok(campaign,'a separate Open control for the campaign');
  const inspect=host.querySelectorAll('[data-work-id="C"]').find(n=>n.dataset.navRole==='inspect');assert.ok(inspect&&inspect!==campaign);
  assert.match(campaign.parent.textContent,/11 contained · 3 need attention · 1 waiting · 7 ready · next: Title T0/);
  assert.equal(campaign.textContent,'View subtasks (2)');
  assert.equal(host.querySelector('.work-flat-catalogue').tag,'details','the flat list is secondary');
  await inspect.click();assert.equal(controller.detail?.task?.id,'C','the campaign itself is inspected as Work');
  const more=findButton(host,'More tasks');await more.click();
  const next=new URL(t.calls.at(-1).url,'http://local').searchParams;
  assert.deepEqual([next.get('view'),next.get('offset'),next.get('as_of')],['roots','12',replies.roots.value.read_cut.revision],'the owner continuation under the exact cut');
  const ids=host.querySelector('.work-navigator-level').querySelectorAll('[data-nav-role="inspect"]').map(n=>n.dataset.workId);
  assert.equal(ids.length,15);assert.equal(new Set(ids).size,15);assert.equal(findButton(host,'More tasks'),undefined,'the exhausted continuation leaves');
 }finally{controller.destroy();dom.restore();}
});

test('opening a branch reads its owner level: breadcrumbs, the node is inspectable, children keep owner order and parallel stays narrow',async()=>{
 const t=owner(),{host,controller,dom}=await mount(t);try{
  await host.querySelector('[data-open-work="C"]').click();
  assert.deepEqual(views(t.calls).slice(-1),['branch']);assert.equal(document.activeElement?.textContent,'Title C','focus lands on the opened level heading');
  await host.querySelector('[data-open-work="B"]').click();
  const level=host.querySelector('.work-navigator-level');
  assert.deepEqual(level.querySelector('.work-nav-crumbs').children.map(n=>n.textContent),['All tasks','Title C']);
  const order=level.querySelector('.work-nav-list').querySelectorAll('[data-nav-role="inspect"]').map(n=>n.dataset.workId);
  assert.ok(order.indexOf('T5')>=0&&order.indexOf('T5')<order.indexOf('T1'),'a sibling prerequisite comes first');
  const row=id=>level.querySelector('.work-nav-list').querySelectorAll('[data-nav-role="inspect"]').find(n=>n.dataset.workId===id).parent.parent;
  assert.ok(row('T0').querySelector('.work-nav-parallel'),'the owner said no declared prerequisite is open');
  assert.equal(row('T1').querySelector('.work-nav-parallel'),null);assert.match(row('T1').textContent,/Waiting on 1 prerequisite/);
  await findButton(level,'More subtasks').click();
  const all=level.querySelector('.work-nav-list').querySelectorAll('[data-nav-role="inspect"]').map(n=>n.dataset.workId);
  assert.deepEqual([...all].sort(),['T0','T1','T2','T3','T4','T5','T6','T7','T8']);
  for(const id of ['T7','T8'])assert.equal(row(id).querySelector('.work-nav-parallel'),null,'a prerequisite cycle is never parallel');
  assert.match(level.textContent,/form a prerequisite cycle/);
  await findButton(level,'Open this task').click();assert.equal(controller.detail.task.id,'B','a branch header inspects the branch itself');
  await findButton(level,'All tasks').click();assert.ok(host.querySelector('[data-open-work="C"]'));
 }finally{controller.destroy();dom.restore();}
});

test('done Work whose acceptance is not current stays in Needs attention, with its containment path',async()=>{
 const t=owner(),{host,controller,dom}=await mount(t);try{
  const attention=host.querySelector('.work-navigator-attention');
  assert.match(attention.textContent,/Needs attention \(3\)/);
  const rows=attention.querySelectorAll('.work-nav-row').map(n=>n.textContent);
  assert.ok(rows.some(text=>/Title A.*Completed — evidence needs rechecking.*In Title C$/.test(text)),'done but not currently accepted: attention, never settled');
  assert.equal(rows.filter(text=>/Prerequisite cycle.*In Title C › Title B/.test(text)).length,2);
 }finally{controller.destroy();dom.restore();}
});

test('a changed cut refuses the continuation, keeps the rows shown and offers a reload of the level',async()=>{
 const t=owner(async url=>{if(/offset=12/.test(url))throw Error('CHANGED_INPUT: Work evidence or membership changed; old pages were not mixed.');}),{host,controller,dom}=await mount(t);try{
  const before=host.querySelector('.work-navigator-level').querySelectorAll('[data-nav-role="inspect"]').length;
  await findButton(host,'More tasks').click();
  assert.equal(host.querySelector('.work-navigator-level').querySelectorAll('[data-nav-role="inspect"]').length,before);
  assert.match(host.querySelector('.work-nav-refusal').textContent,/CHANGED_INPUT/);assert.ok(findButton(host,'Reload this level'));
  assert.equal(document.activeElement,findButton(host,'Reload this level'),'the attached reload takes the keyboard focus');
 }finally{controller.destroy();dom.restore();}
});

test('Needs, Affects and Contains share one panel; a tab change keeps focus on the tab and reads nothing',async()=>{
 const t=owner(),{host,controller,dom}=await mount(t,{initialWork:'B'});try{
  const panel=host.querySelector('.operator-work-relations'),tabs=panel.querySelectorAll('[role="tab"]');
  assert.deepEqual(tabs.map(n=>n.textContent),['Needs (0)','Affects (0)','Contains (9)']);
  const panels=panel.querySelector('.work-relations-panels').children;assert.equal(panels.length,3,'one container holds all three');
  assert.equal(tabs[2].attrs['aria-selected'],'true');assert.equal(panels[2].hidden,false);assert.equal(panels[0].hidden,true);
  const count=t.calls.length;await tabs[0].click();
  assert.equal(document.activeElement,tabs[0],'focus stays on the activated tab');assert.equal(panels[0].hidden,false);assert.equal(panels[2].hidden,true);assert.equal(t.calls.length,count,'no reread for a tab');
  tabs[0].onkeydown({key:'End',preventDefault(){}});assert.equal(document.activeElement,tabs[2],'the keyboard moves focus to the activated tab');assert.equal(panels[2].hidden,false);
  assert.match(panels[2].textContent,/6 of 9 shown/);await findButton(panels[2],'More contained work').click();
  assert.equal(panels[2].querySelectorAll('li').length,9);assert.match(t.calls.at(-1).url,/as_of=/);
 }finally{controller.destroy();dom.restore();}
});

test('opening related Work offers Return, which reselects the opener and lands on the same tab',async()=>{
 const t=owner(),{host,controller,dom}=await mount(t,{initialWork:'B'});try{
  const contains=host.querySelector('.operator-work-relations').querySelectorAll('[role="tab"]')[2];
  const child=host.querySelector('.work-relations-panels').children[2].querySelectorAll('button').find(n=>n.textContent==='Title T1');
  await child.click();assert.equal(controller.detail.task.id,'T1');
  const back=host.querySelector('[data-relation-return="B"]');assert.ok(back);assert.equal(back.textContent,'Return to Title B · Contains');
  assert.match(host.querySelector('.operator-work-relations').textContent,/Needs \(1\)/);
  await back.click();assert.equal(controller.detail.task.id,'B');
  const tab=host.querySelector('.operator-work-relations').querySelectorAll('[role="tab"]')[2];
  assert.notEqual(tab,contains,'the panel was repainted for the reselected Work');
  assert.equal(tab.attrs['aria-selected'],'true');assert.equal(document.activeElement,tab,'focus returns to the same tab, not the heading');
 }finally{controller.destroy();dom.restore();}
});

test('every grade shows its owner descriptor and the follow-up form explains itself from the owner composition',async()=>{
 const t=owner(),{host,controller,dom}=await mount(t,{initialWork:'C'});try{
  const context=()=>host.querySelector('.work-action-context').textContent;
  assert.match(context(),/Actions and context \(campaign\)/);
  assert.match(context(),/Consumes expected_dependency_revision, expected_work_scope_revision, expected_work_status_revision\. Effects: /);
  assert.match(context(),/Refused now: cancelled — only session-request and dispatch tasks can be cancelled/,'the owner refusal, from the one carrier');
  await controller.select('T0');assert.match(context(),/\(task\)/);
  await controller.select('RV');
  const recorder=host.querySelector('.operator-review-recorder'),choose=recorder.querySelector('select');
  assert.deepEqual(choose.children.map(n=>n.textContent),Object.values(replies.detailRV.value.allowed_actions.work_review.preparation.phases).map(p=>p.title));
  choose.value='followup';choose.onchange();
  const composition=replies.detailRV.value.allowed_actions.work_review.preparation.phases.followup.composition;
  const note=host.querySelector('.work-composition');assert.ok(note);assert.deepEqual(note.querySelectorAll('li').map(n=>n.textContent),composition.steps.map(step=>step.effect));
  const closure=recorder.querySelectorAll('select').find(n=>n.name==='closure');closure.value='prerequisite';closure.onchange();
  assert.match(note.textContent,new RegExp('This closure: '+composition.closures.prerequisite));
  choose.value='review';choose.onchange();
  assert.match(recorder.textContent,/No handoff is recorded yet/);assert.equal(recorder.querySelector('[data-review-submit]').disabled,true,'the owner refusal disables only this phase');
 }finally{controller.destroy();dom.restore();}
});

test('one changed owner condition changes the agent-visible preparation and the real human control together',async()=>{
 const strict=replies.detailT0_strict.value,agent=replies.agentT0_strict.value;
 assert.ok(!agent.statuses.includes('in-progress')&&agent.refused['in-progress']==='This fixture owner forbids starting Work.');
 for(const [value,forbidden] of [[replies.detailT0.value,false],[strict,true]]){
  const t=owner(async url=>/view=detail/.test(url)&&/id=T0/.test(url)?value:undefined),{host,controller,dom}=await mount(t,{initialWork:'T0'});try{
   const form=host.querySelector('[data-control="work:disposition"]'),options=form.querySelector('select').children.map(n=>n.value);
   assert.equal(options.includes('in-progress'),!forbidden);
   assert.equal(/Not available now: Mark in progress \(declaration\) — This fixture owner forbids starting Work\./.test(form.textContent),forbidden);
   if(forbidden)assert.deepEqual(options,agent.statuses,'the person is offered exactly what the agent is offered');
  }finally{controller.destroy();dom.restore();}
 }
});

test('an external phase reaches an open dirty Work view: review status updates, the dirty form keeps text, guard and request',async()=>{
 const after=replies.detailRV_after.value;let current=replies.detailRV.value;
 const t=owner(async url=>/view=detail/.test(url)&&/id=RV/.test(url)?current:undefined),{host,controller,dom}=await mount(t,{initialWork:'RV'});try{
  const recorder=host.querySelector('.operator-review-recorder'),choose=recorder.querySelector('select');choose.value='followup';choose.onchange();
  const form=recorder.querySelector('form'),finding=form.querySelectorAll('input').find(n=>n.name==='finding');finding.value='UNSENT FINDING';form.oninput();
  const held=structuredClone(controller.capture().drafts.RV.review);
  const disposition=host.querySelector('[data-control="work:disposition"]');
  current=after;await controller.observed({changes:['records','selected']});
  const review=host.querySelector('[data-control="work:review"]');
  assert.match(review.textContent,/Handed off by author \(human\)/,'the external handoff is shown without reselecting');
  assert.equal(host.querySelector('.operator-review-recorder').querySelector('form'),form,'the dirty recorder form stays mounted');
  assert.equal(finding.value,'UNSENT FINDING');assert.deepEqual(controller.capture().drafts.RV.review,held,'text, request id and consumed basis are kept');
  assert.notEqual(host.querySelector('[data-control="work:disposition"]'),disposition,'a clean read-only/form part is replaced by the fresh one');
  assert.ok(!form.querySelector('[data-review-submit]').disabled,'a handoff does not change what a follow-up consumes: the draft stays usable');
  assert.match(host.querySelector('.work-status').textContent,/consumed guards are unchanged/);
  current=replies.detailRV_edited.value;await controller.observed({changes:['records','selected']});
  assert.equal(host.querySelector('.operator-review-recorder').querySelector('form'),form);assert.equal(finding.value,'UNSENT FINDING');
  assert.equal(form.querySelector('[data-review-submit]').disabled,true,'the specification guard this draft consumed changed: only this form is disabled');
  assert.ok(form.querySelector('[data-adopt-basis]'),'explicit adoption is offered');assert.match(host.querySelector('.work-status').textContent,/basis your review draft consumed changed/);
  await form.querySelector('[data-adopt-basis]').click();
  const adopted=controller.capture().drafts.RV.review;
  assert.deepEqual(adopted.basis,current.allowed_actions.work_review.preparation.phases.followup.basis);assert.notEqual(adopted.request_id,held.request_id,'adoption is a new request');
  assert.equal(adopted.fields.finding,'UNSENT FINDING');
  assert.ok(!t.calls.some(call=>call.payload),'nothing was posted');
 }finally{controller.destroy();dom.restore();}
});

test('focus inside a part keeps that part mounted while the other read-only parts refresh',async()=>{
 const after=structuredClone(replies.detailT0.value);after.task.status='in-progress';after.task.recorded_status='in-progress';after.task.lifecycle={...after.task.lifecycle,status:'in-progress'};
 let current=replies.detailT0.value;
 const t=owner(async url=>/view=detail/.test(url)&&/id=T0/.test(url)?current:undefined),{host,controller,dom}=await mount(t,{initialWork:'T0'});try{
  const relations=host.querySelector('.operator-work-relations'),tab=relations.querySelectorAll('[role="tab"]')[1];tab.focus();
  current=after;await controller.observed({changes:['selected']});
  assert.equal(host.querySelector('.operator-work-relations'),relations,'the focused relationships part is kept');assert.equal(document.activeElement,tab,'focus stays');
  assert.match(host.querySelector('.operator-work-heading').textContent,/In progress \(declared\)/,'the standing still refreshes');
 }finally{controller.destroy();dom.restore();}
});

test('a failed owner read throws so the observer delivers the same hint again; a later success applies it',async()=>{
 let fail=true,current=replies.detailT0.value;const moved=structuredClone(current);moved.task.status='in-progress';moved.task.recorded_status='in-progress';moved.task.lifecycle={...moved.task.lifecycle,status:'in-progress'};
 const t=owner(async url=>{if(/view=detail/.test(url)&&/id=T0/.test(url)){if(current===moved&&fail){fail=false;throw Error('owner restarting');}return current;}}),{host,controller,dom}=await mount(t,{initialWork:'T0'});try{
  current=moved;await assert.rejects(controller.observed({changes:['selected']}),/owner restarting/);
  assert.doesNotMatch(host.querySelector('.operator-work-heading').textContent,/In progress \(declared\)/);
  await controller.observed({changes:['selected']});assert.match(host.querySelector('.operator-work-heading').textContent,/In progress \(declared\)/);
 }finally{controller.destroy();dom.restore();}
});

test('the observer reads a baseline, backs off while unchanged, resets on change, pauses hidden, honours expiry and stops',async()=>{
 const timers=[],reads=[],changes=[];let now=0,reply=()=>({project:'p',view:'observe',token:'wo1.a.b.c',changed:reads.length>1?false:null,poll:{after_ms:5000,max_ms:60000,backoff:2}});
 const clock={setTimeout:(fn,ms)=>{const t={fn,ms};timers.push(t);return t;},clearTimeout:t=>{const at=timers.indexOf(t);if(at>=0)timers.splice(at,1);},now:()=>now};
 const listeners={};const doc={visibilityState:'visible',addEventListener:(k,fn)=>{listeners[k]=fn;},removeEventListener:k=>{delete listeners[k];}};
 const observer=observeWork({project:'p',request:async url=>{reads.push(url);return reply();},selected:()=>'B',isCurrent:()=>true,onChange:v=>changes.push(v),clock,doc});
 const run=async()=>{const t=timers.shift();await t.fn();return t.ms;};
 assert.equal(await run(),0);assert.doesNotMatch(reads[0],/since=/);assert.equal(changes.length,0,'the first read is a baseline');
 assert.equal(timers[0].ms,5000);await run();assert.match(reads[1],/since=wo1\.a\.b\.c/);assert.equal(timers[0].ms,10000);
 await run();assert.equal(timers[0].ms,20000);await run();await run();assert.equal(timers[0].ms,60000,'bounded backoff');
 reply=()=>({project:'p',view:'observe',token:'wo1.x.b.c',changed:true,changes:['records'],poll:{after_ms:5000,max_ms:60000,backoff:2}});
 await run();assert.equal(changes.length,1);assert.equal(timers[0].ms,5000,'a change resets the delay');
 reply=()=>({project:'p',view:'observe',token:'wo1.x.b.c',changed:false,expires_next_at:new Date(now+3000).toISOString(),poll:{after_ms:5000,max_ms:60000,backoff:2}});
 await run();assert.equal(timers[0].ms,3250,'the next read is brought forward to the owner expiry');
 doc.visibilityState='hidden';listeners.visibilitychange();assert.equal(timers.length,0,'nothing runs while hidden');
 doc.visibilityState='visible';listeners.visibilitychange();assert.equal(timers[0].ms,0,'visible again reads at once');
 observer.stop();assert.equal(timers.length,0);assert.equal(listeners.visibilitychange,undefined);
 assert.ok(reads.every(url=>/view=observe/.test(url)),'the observer only reads');
});

test('a page hidden while a read is in flight schedules nothing when the reply lands',async()=>{
 let release;const timers=[],doc={visibilityState:'visible',addEventListener(){},removeEventListener(){}};
 const clock={setTimeout:(fn,ms)=>{const t={fn,ms};timers.push(t);return t;},clearTimeout:t=>{const at=timers.indexOf(t);if(at>=0)timers.splice(at,1);},now:()=>0};
 observeWork({project:'p',request:async()=>new Promise(resolve=>{release=resolve;}),selected:()=>'A',isCurrent:()=>true,onChange:()=>{},clock,doc});
 const pending=timers.shift().fn();doc.visibilityState='hidden';release({project:'p',view:'observe',token:'wo1.a.a.a',changed:null});await pending;
 assert.equal(timers.length,0,'no timer is armed while hidden');
});

test('a late observer reply after stop or a selection change reports nothing',async()=>{
 let release,selected='A';const changes=[],timers=[];
 const clock={setTimeout:(fn,ms)=>{const t={fn,ms};timers.push(t);return t;},clearTimeout:t=>{const at=timers.indexOf(t);if(at>=0)timers.splice(at,1);},now:()=>0};
 const observer=observeWork({project:'p',request:async()=>new Promise(resolve=>{release=resolve;}),selected:()=>selected,isCurrent:()=>true,onChange:v=>changes.push(v),clock,doc:null});
 const first=timers.shift().fn();release({project:'p',view:'observe',token:'wo1.a.a.a',changed:null});await first;
 const second=timers.shift().fn();selected='B';release({project:'p',view:'observe',token:'wo1.a.b.a',changed:true,changes:['selected']});await second;
 assert.equal(changes.length,0,'a hint for the previous selection is dropped');
 const third=timers.shift().fn();observer.stop();release({project:'p',view:'observe',token:'wo1.z.z.z',changed:true});await third;
 assert.equal(changes.length,0);assert.equal(timers.length,0);
});

test('the standing chip prints the owner group and its leading fact, never a guessed label',()=>{
 assert.deepEqual(standingChip({standing:{group:'attention',facts:[{code:'done-review-required',text:'Done; acceptance review required'}]}}),{label:'Completed — evidence needs rechecking',tone:'attention'});
 assert.deepEqual(standingChip({standing:{group:'ready',facts:[{code:'ready',text:'Ready'}]}}),{label:'Ready',tone:'ok'});
 assert.deepEqual(standingChip({status:'open'},()=>({label:'fallback',tone:'neutral'})),{label:'fallback',tone:'neutral'});
});

// ---- repair1 WI-R3: delivery basis ----
const fakeClock=()=>{const timers=[];return {timers,clock:{setTimeout:(fn,ms)=>{const t={fn,ms};timers.push(t);return t;},clearTimeout:t=>{const at=timers.indexOf(t);if(at>=0)timers.splice(at,1);},now:()=>0},
  run:async()=>{const t=timers.shift();await t.fn();return t.ms;}};};
test('Sol WI-R3 witness: a failed delivery does not advance the token, so the next read delivers the same change',async()=>{
 const {timers,clock,run}=fakeClock(),reads=[],delivered=[];let ownerToken='wo1.A.s.a',fail=true;
 const request=async url=>{const since=new URL(url,'http://local').searchParams.get('since');reads.push(since);
  return since?{project:'p',view:'observe',token:ownerToken,changed:since!==ownerToken,...(since!==ownerToken?{changes:['records','selected']}:{})}:{project:'p',view:'observe',token:ownerToken,changed:null,poll:{after_ms:5000,max_ms:60000,backoff:2}};};
 const observer=observeWork({project:'p',request,selected:()=>'B',isCurrent:()=>true,clock,doc:null,
  onChange:async value=>{if(fail){fail=false;throw Error('transient view-read failure');}delivered.push(value.token);}});
 await run();assert.equal(observer.state().token,'wo1.A.s.a');
 ownerToken='wo1.B.s.a';await run();
 assert.equal(observer.state().token,'wo1.A.s.a','the failed delivery kept the applied token');assert.equal(observer.state().failures,1);
 await run();assert.deepEqual(reads,[null,'wo1.A.s.a','wo1.A.s.a'],'the next read asks since the applied token, with no new owner event');
 assert.deepEqual(delivered,['wo1.B.s.a']);assert.equal(observer.state().token,'wo1.B.s.a');observer.stop();assert.equal(timers.length,0);
});
test('a change between the mounted detail read and the first observation is delivered at the baseline',async()=>{
 const {clock,run}=fakeClock(),delivered=[];
 const observer=observeWork({project:'p',request:async()=>({project:'p',view:'observe',token:'wo1.NEWREC.sel.act',changed:null}),selected:()=>'B',isCurrent:()=>true,clock,doc:null,
  basis:()=>({records:'OLDREC',selected:'sel',activity:'act'}),onChange:async value=>{delivered.push(value.changes);}});
 await run();assert.deepEqual(delivered,[['records']]);
 const quiet=observeWork({project:'p',request:async()=>({project:'p',view:'observe',token:'wo1.R.s.a',changed:null}),selected:()=>'B',isCurrent:()=>true,clock,doc:null,
  basis:()=>({records:'R',selected:'s',activity:'a'}),onChange:async()=>assert.fail('nothing changed')});
 await run();observer.stop();quiet.stop();
});
test('the controller publishes the observe basis its mounted reads consumed',async()=>{
 const t=owner(),{controller,dom}=await mount(t,{initialWork:'T0'});try{
  assert.deepEqual(controller.observeBasis(),replies.detailT0.value.observe_basis);assert.ok(controller.observeBasis().selected);
 }finally{controller.destroy();dom.restore();}
});

// ---- repair1 WI-R4: navigator continuation fences and coverage ----
async function openB(extra){const t=owner(extra),m=await mount(t);await m.host.querySelector('[data-open-work="C"]').click();await m.host.querySelector('[data-open-work="B"]').click();return {t,...m};}
const levelIds=host=>host.querySelector('.work-navigator-level').querySelector('.work-nav-list').querySelectorAll('[data-nav-role="inspect"]').map(n=>n.dataset.workId);
for(const [name,mutate,before] of [
 ['Sol WI-R4 witness: next_read naming another branch',page=>{page.pagination.next_read.http.url=page.pagination.next_read.http.url.replace('id=B','id=C');},true],
 ['a non-advancing continuation',page=>{page.pagination.next_read.http.url=page.pagination.next_read.http.url.replace(/offset=\d+/,'offset='+page.pagination.offset);},true],
 ['another cut in next_read',page=>{page.pagination.next_read.http.url=page.pagination.next_read.http.url.replace(/as_of=[^&]+/,'as_of=moved');},true],
 ['a reply for another branch at the right URL',null,false],
])test('navigator refuses '+name+', keeps rows and offers an attached reload',async()=>{
 const wrong=structuredClone(replies.branchC.value);
 const {t,host,controller,dom}=await openB(async url=>{const q=new URL(url,'http://local').searchParams;
  if(q.get('view')==='branch'&&q.get('id')==='B'&&!q.get('offset')){const page=structuredClone(replies.branchB.value);page.pagination.offset=0;if(mutate)mutate(page);return page;}
  if(!mutate&&q.get('view')==='branch'&&q.get('offset'))return {...wrong,pagination:{...wrong.pagination,offset:Number(q.get('offset'))}};});try{
  const shown=levelIds(host),calls=t.calls.length;const more=findButton(host,'More subtasks');more.focus();await more.click();
  assert.deepEqual(levelIds(host),shown,'no row of another level or page was mixed in');
  if(before)assert.equal(t.calls.length,calls,'refused before any owner read');
  assert.ok(host.querySelector('.work-nav-refusal'));assert.equal(document.activeElement,findButton(host,'Reload this level'));
  await findButton(host,'Reload this level').click();assert.equal(host.querySelector('.work-nav-refusal'),null,'reload paints the level afresh');
 }finally{controller.destroy();dom.restore();}
});
test('a valid page whose rows are all shown already adds nothing and says so; duplicates are never painted twice',async()=>{
 const {host,controller,dom}=await openB(async url=>{const q=new URL(url,'http://local').searchParams;
  if(q.get('view')==='branch'&&q.get('offset')){const page=structuredClone(replies.branchB2.value);page.children=structuredClone(replies.branchB.value.children).slice(0,3);return page;}});try{
  const shown=levelIds(host);const more=findButton(host,'More subtasks');more.focus();await more.click();
  assert.deepEqual(levelIds(host),shown);assert.match(host.querySelector('.work-nav-none').textContent,/added no new Work/);assert.equal(document.activeElement,host.querySelector('.work-nav-none'));
 }finally{controller.destroy();dom.restore();}
});
test('a continuation landing after the person opened another level is dropped',async()=>{
 let release;const {host,controller,dom}=await openB(async url=>{const q=new URL(url,'http://local').searchParams;
  if(q.get('view')==='branch'&&q.get('offset'))return new Promise(resolve=>{release=()=>resolve(structuredClone(replies.branchB2.value));});});try{
  const pending=findButton(host,'More subtasks').click();await new Promise(resolve=>setImmediate(resolve));
  await findButton(host,'All tasks').click();release();await pending;
  assert.equal(host.querySelector('.work-navigator-level').querySelector('h3').textContent,'Tasks');assert.ok(!levelIds(host).includes('T6'));
 }finally{controller.destroy();dom.restore();}
});
test('a refresh rereads every page shown under one cut and keeps the coverage and the focused row',async()=>{
 const {t,host,controller,dom}=await openB();try{
  await findButton(host,'More subtasks').click();const shown=levelIds(host);assert.equal(shown.length,9);
  const focusedRow=host.querySelector('.work-navigator-level').querySelectorAll('[data-nav-role="inspect"]').find(n=>n.dataset.workId==='T7');focusedRow.focus();
  const calls=t.calls.length;await controller.refreshNavigation();
  assert.deepEqual(levelIds(host),shown,'no silent loss of the second page');
  const reread=t.calls.slice(calls).map(c=>new URL(c.url,'http://local').searchParams).filter(q=>q.get('view')==='branch');
  assert.deepEqual(reread.map(q=>q.get('offset')),[null,'6'],'page one, then the continuation');assert.equal(reread[1].get('as_of'),replies.branchB.value.read_cut.revision);
  assert.equal(document.activeElement.dataset.workId,'T7','focus stays on the same Work control');
 }finally{controller.destroy();dom.restore();}
});
test('deep ancestry is disclosed with its root, never implied complete',async()=>{
 const deep=replies.branchD13.value,rows=structuredClone(replies.roots.value);rows.roots=[{...deep.node,child_count:1}];rows.pagination={...rows.pagination,total:1,returned:1,next_offset:null,next_read:null};
 const t=owner(async url=>/view=roots/.test(url)?rows:undefined),{host,controller,dom}=await mount(t);try{
  await host.querySelector('[data-open-work="D13"]').click();
  const crumbs=host.querySelector('.work-nav-crumbs');
  assert.match(crumbs.textContent,new RegExp('… '+deep.breadcrumbs_omitted+' more containing Work …'));
  assert.ok(crumbs.querySelectorAll('button').some(n=>n.textContent===deep.breadcrumbs_root.title),'the root to descend from is offered');
  assert.equal(crumbs.querySelectorAll('button').length,2+deep.breadcrumbs.length);
 }finally{controller.destroy();dom.restore();}
});

// ---- repair2 WI-R4a: refresh and attention refresh read continuations only through the one admission ----
const reads=(t,from=0)=>t.calls.slice(from).map(c=>new URL(c.url,'http://local').searchParams);
async function refreshed(mutate){
 let refresh=false;const {t,host,controller,dom}=await openB(async url=>{const q=new URL(url,'http://local').searchParams;
  if(refresh&&q.get('view')==='branch'&&q.get('id')==='B'&&!q.get('offset')){const page=structuredClone(replies.branchB.value);return mutate.first?mutate.first(page)||page:page;}
  if(refresh&&q.get('view')==='branch'&&q.get('offset')&&mutate.next)return mutate.next(structuredClone(replies.branchB2.value),q);});
 await findButton(host,'More subtasks').click();const shown=levelIds(host);assert.equal(shown.length,9);
 refresh=true;const from=t.calls.length;let error=null;try{await controller.refreshNavigation();}catch(caught){error=caught;}
 return {t,host,controller,dom,shown,from,error};
}
const nextUrl=(page,edit)=>{page.pagination.next_read.http.url=edit(page.pagination.next_read.http.url);return page;};
for(const [name,edit] of [
 ['Sol WI-R4a witness: next_read naming another branch',url=>url.replace('id=B','id=C')],
 ['another project',url=>url.replace('project=p','project=q')],
 ['another path',url=>url.replace('/work/state','/work/other')],
 ['another view',url=>url.replace('view=branch','view=roots')],
 ['another cut',url=>url.replace(/as_of=[^&]+/,'as_of=moved')],
 ['a non-advancing offset',url=>url.replace(/offset=\d+/,'offset=0')],
])test('a refresh refuses '+name+' before any read, keeps the rows and attaches a reload',async()=>{
 const {t,host,controller,dom,shown,from,error}=await refreshed({first:page=>nextUrl(page,edit)});try{
  assert.ok(error,'the refresh is refused');
  assert.deepEqual(reads(t,from).filter(q=>q.get('view')==='branch').map(q=>q.get('offset')),[null],'only the first page was read; the invalid continuation never was');
  assert.ok(!reads(t,from).some(q=>q.get('id')==='C'),'zero reads of another branch');
  assert.deepEqual(levelIds(host),shown);assert.ok(host.querySelector('.work-nav-refusal')&&findButton(host,'Reload this level'));
 }finally{controller.destroy();dom.restore();}
});
test('a refresh with a non-GET continuation is refused before any read',async()=>{
 const {t,controller,dom,from,error}=await refreshed({first:page=>{page.pagination.next_read.http.method='POST';return page;}});try{
  assert.ok(error);assert.equal(reads(t,from).filter(q=>q.get('view')==='branch').length,1);
 }finally{controller.destroy();dom.restore();}
});
for(const [name,next] of [
 ['another branch node',page=>({...structuredClone(replies.branchC.value),pagination:page.pagination})],
 ['another project',page=>({...page,project:'q'})],
 ['another page offset',page=>({...page,pagination:{...page.pagination,offset:7}})],
])test('a refresh refuses a reply with '+name+' before counting it',async()=>{
 const {host,controller,dom,shown,error}=await refreshed({next:page=>next(page)});try{
  assert.ok(error);assert.deepEqual(levelIds(host),shown,'nothing of the refused reply is painted');
 }finally{controller.destroy();dom.restore();}
});
test('a refresh whose cut moves restarts once and succeeds; a second move refuses',async()=>{
 let moves=1;const once=await refreshed({next:page=>moves-->0?{...page,read_cut:{revision:'moved'}}:page});try{
  assert.equal(once.error,null);assert.deepEqual(levelIds(once.host),once.shown);
  assert.deepEqual(reads(once.t,once.from).filter(q=>q.get('view')==='branch').map(q=>q.get('offset')),[null,'6',null,'6'],'one bounded restart');
 }finally{once.controller.destroy();once.dom.restore();}
 const always=await refreshed({next:page=>({...page,read_cut:{revision:'moved'}})});try{
  assert.ok(always.error?.moved);assert.equal(reads(always.t,always.from).filter(q=>q.get('view')==='branch').length,4,'finite: two attempts');
  assert.deepEqual(levelIds(always.host),always.shown);
 }finally{always.controller.destroy();always.dom.restore();}
});
test('a refresh page of only duplicates ends finitely and keeps the shown rows',async()=>{
 const {host,controller,dom,shown,error}=await refreshed({next:page=>({...page,children:structuredClone(replies.branchB.value.children)})});try{
  assert.equal(error,null);assert.deepEqual([...levelIds(host)].sort(),[...shown.slice(0,6)].sort(),'no row painted twice; the owner page added nothing new');
 }finally{controller.destroy();dom.restore();}
});
test('the attention refresh reads its continuation only through the same admission',async()=>{
 const attention=structuredClone(replies.roots.value.attention);
 if(!attention.next_read){attention.next_read={operation:'project',payload:{},http:{method:'GET',url:'/work/state?'+new URLSearchParams({project:'p',view:'attention',offset:String(attention.covered??attention.returned),limit:'6',as_of:replies.roots.value.read_cut.revision})}};}
 let refresh=false;const rootsPage=()=>{const page=structuredClone(replies.roots.value);page.attention=structuredClone(attention);
  if(refresh)page.attention.next_read.http.url=page.attention.next_read.http.url.replace('view=attention','view=attention&id=C');return page;};
 const more={...structuredClone(replies.attention.value),read_cut:structuredClone(replies.roots.value.read_cut),pagination:{...replies.attention.value.pagination,offset:attention.covered??attention.returned,next_read:null}};
 const t=owner(async url=>{const q=new URL(url,'http://local').searchParams;if(q.get('view')==='roots'&&!q.get('offset'))return rootsPage();if(q.get('view')==='attention')return {...more,tasks:[{...structuredClone(attention.items[0]),id:'EXTRA'}]};}),{host,controller,dom}=await mount(t);try{
  const control=findButton(host,'More needing attention');await control.click();
  assert.ok(host.querySelector('.work-navigator-attention').querySelectorAll('[data-work-id="EXTRA"]').length,'the explicit More added one row');
  refresh=true;const from=t.calls.length;await assert.rejects(controller.refreshNavigation());
  assert.ok(!reads(t,from).some(q=>q.get('view')==='attention'),'the invalid attention continuation was never read');
 }finally{controller.destroy();dom.restore();}
});

// THE TASK FILTERS (wave 8): every filter but All tasks is the owner's list of that group at every depth (view:group) under the
// page's cut; the counts are the owner's counts.groups and add up to the task total; More continues through nextPage; a
// refresh reads the chosen list again as far as it was paged; a refused read is drawn in place; All tasks is left as it was.
async function tasksPage(t){
 const dom=installDOM(),host=new Node('section');dom.body.append(host);const selections=[];
 const controller=await mountOperatorWork(host,{project:'p',summary:{project:'p',view:'summary',tasks:[],counts:{pending:4,completed:2,completed_review_required:1}},request:t.request,navigation:true,page:true,onSelect:task=>selections.push(task?.id||null)});
 return {dom,host,controller,selections};
}
const groupIds=host=>host.querySelector('.work-navigator-group').querySelectorAll('[data-nav-role="inspect"]').map(n=>n.dataset.workId);
test('the Tasks filters: each lists the owner group at every depth, its count adds up, More pages it and a refresh keeps it',async()=>{
 const t=owner(),{dom,host,controller}=await tasksPage(t);try{
  const counts=host.querySelectorAll('.work-nav-filter').slice(1).map(n=>Number(/\((\d+)\)$/.exec(n.textContent)[1]));
  assert.equal(counts.reduce((a,b)=>a+b,0),replies.roots.value.counts.work,'the filter counts add up to the task total');
  assert.match(host.querySelector('.task-page-counts').textContent,new RegExp('^'+replies.roots.value.counts.work+' tasks'));
  const from=t.calls.length;await findButton(host,'Ready (22)').click();
  const q=new URL(t.calls[from].url,'http://local').searchParams;
  assert.deepEqual([q.get('view'),q.get('group'),q.get('as_of')],['group','ready',replies.roots.value.read_cut.revision],'the group read under the page cut');
  assert.equal(groupIds(host).length,replies['group-ready'].value.tasks.length);
  const deep=host.querySelector('.work-navigator-group').querySelectorAll('[data-work-id="T0"]')[0].parent.parent;
  assert.match(deep.textContent,/In Title C › Title B/,'a subtask inside a task group is listed with its containing path');
  await findButton(host.querySelector('.work-navigator-group'),'More tasks').click();
  const all=groupIds(host),owned=[...replies['group-ready'].value.tasks,...replies['group-ready2'].value.tasks].map(row=>row.id);
  assert.deepEqual(all,owned,'the page lists exactly the owner group, in its order');assert.equal(all.length,22);
  assert.equal(host.querySelector('.work-navigator-group').querySelector('.work-nav-more'),null,'More leaves at the end');
  const before=t.calls.length;await controller.refreshNavigation();
  const reread=t.calls.slice(before).map(c=>new URL(c.url,'http://local').searchParams).filter(p=>p.get('view')==='group');
  assert.deepEqual(reread.map(p=>[p.get('group'),p.get('offset')]),[['ready',null],['ready','12']],'a refresh reads the chosen list again as far as it was paged');
  assert.deepEqual(groupIds(host),owned);
  await findButton(host,'Closed (0)').click();
  assert.equal(host.querySelector('.work-navigator-group').querySelector('.work-nav-none').textContent,'No task is in Closed at this read.');
  await findButton(host,'All tasks').click();assert.equal(host.querySelector('.work-navigator-group').hidden,true);assert.equal(host.querySelector('.work-navigator-level').hidden,false);
 }finally{controller.destroy();dom.restore();}
});
test('the Tasks filters keep the nested list and the open task as left, and draw a refused group read in place',async()=>{
 let refuse=false;
 const t=owner(async url=>{if(refuse&&new URL(url,'http://local').searchParams.get('view')==='group')throw Error('Work evidence or membership changed; old pages were not mixed.');}),{dom,host,controller,selections}=await tasksPage(t);try{
  const open=host.querySelector('[data-open-work="C"]');await open.click();assert.equal(open.textContent,'Hide subtasks (2)');
  const inspect=host.querySelectorAll('[data-work-id="C"]').find(n=>n.dataset.navRole==='inspect');await inspect.click();assert.equal(controller.detail?.task?.id,'C');
  await findButton(host,'Waiting (1)').click();assert.equal(controller.detail?.task?.id,'C','choosing a filter leaves the open task beside the list');
  assert.deepEqual(groupIds(host),replies['group-blocked'].value.tasks.map(row=>row.id));
  const chosen=host.querySelector('.work-navigator-group').querySelectorAll('[data-work-id]')[0];
  await chosen.click();assert.equal(chosen.getAttribute('aria-current'),'true','a row of the group list opens like any row and is marked chosen');
  refuse=true;await findButton(host,'Ready (22)').click();
  assert.equal(host.querySelector('.work-navigator-group').querySelector('.work-nav-refusal').textContent,'Work evidence or membership changed; old pages were not mixed.');
  assert.ok(findButton(host,'Reload this level'),'the refusal offers the one reload');
  refuse=false;await findButton(host,'All tasks').click();
  assert.equal(host.querySelector('[data-open-work="C"]').textContent,'Hide subtasks (2)','the nested list is where he left it');
  assert.equal(selections.includes(null),false);
 }finally{controller.destroy();dom.restore();}
});

// THE TASKS PAGE (frontend redesign wave 5): page mode draws filters in the owner's group words, shows a group's subtasks in
// place under its row from the owner's branch page, and opens one task beside the list with Close; nothing is counted here.
test('the Tasks page: filters in the owner group words, subtasks in place under the row, and Close on the open task',async()=>{
 const t=owner(),dom=installDOM(),host=new Node('section');dom.body.append(host);const selections=[];
 const controller=await mountOperatorWork(host,{project:'p',summary:{project:'p',view:'summary',tasks:[],counts:{pending:4,completed:2,completed_review_required:1}},request:t.request,navigation:true,page:true,onSelect:task=>selections.push(task?.id||null)});
 try{
  assert.equal(host.querySelector('.task-catalogue-browser').tag,'section','the list is on the page, not behind a disclosure');
  assert.match(host.querySelector('.task-page-counts').textContent,/^\d+ tasks? · \d+ task groups?$/,'the owner line under the title');
  assert.equal(host.querySelector('.task-page-summary').textContent,'4 pending tasks · 2 recorded completions · 1 completed tasks need current review.');
  const filters=host.querySelectorAll('.work-nav-filter').map(n=>n.textContent);
  assert.deepEqual(filters,['All tasks','Needs attention (3)','In progress (declared) (0)','Ready (22)','Awaiting review (0)','Waiting (1)','Closed (0)'],'every group with the owner count of it');
  assert.equal(host.querySelectorAll('.work-nav-filter')[0].getAttribute('aria-pressed'),'true');
  const calls=t.calls.length;await findButton(host,'Needs attention (3)').click();
  assert.deepEqual(views(t.calls.slice(calls)),['group'],'choosing a filter reads that group\'s owner list once');
  assert.equal(host.querySelector('.work-navigator').dataset.filter,'attention');assert.equal(host.querySelector('.work-navigator-level').hidden,true);
  assert.equal(host.querySelector('.work-navigator-group').hidden,false);assert.equal(host.querySelector('.work-navigator-attention').hidden,true);
  await findButton(host,'All tasks').click();assert.equal(host.querySelector('.work-navigator-level').hidden,false);
  assert.ok(host.querySelector('.work-nav-groups').querySelector('[data-open-work="C"]'),'the task group sits under Task groups');
  const open=host.querySelector('[data-open-work="C"]');await open.click();
  assert.deepEqual(views(t.calls).slice(-1),['branch'],'its owner branch page is read');
  assert.equal(open.textContent,'Hide subtasks (2)');assert.equal(open.getAttribute('aria-expanded'),'true');
  const box=host.querySelector('[data-subtasks-of="C"]');assert.ok(box&&open.parent.children.includes(box),'the subtasks are shown under their row');
  assert.ok(box.querySelectorAll('[data-nav-role="inspect"]').length>=1);assert.equal(host.querySelector('.work-nav-crumbs'),null,'the list was not replaced');
  await open.click();assert.equal(box.hidden,true);assert.equal(open.textContent,'View subtasks (2)');assert.equal(open.getAttribute('aria-expanded'),'false');
  const inspect=host.querySelectorAll('[data-work-id="C"]').find(n=>n.dataset.navRole==='inspect');await inspect.click();
  assert.equal(controller.detail?.task?.id,'C');const close=host.querySelector('.task-close');assert.ok(close,'Close at the open task');
  assert.equal(host.querySelector('.task-catalogue-browser').hidden,undefined,'the list stays on the page beside the open task');
  await close.click();assert.equal(selections.at(-1),null,'Close clears the selection');assert.ok(!host.className.includes('task-selected'));
 }finally{controller.destroy();dom.restore();}
});
