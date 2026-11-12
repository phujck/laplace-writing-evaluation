"""Actual Work catalogue/planning, public roots, no provider or history body reads."""
import copy,json
from pathlib import Path
import pytest
from laplace.work import project_work as W,backlog as B,project_work_views as V


def seed(root,project,ident,**kw):
 return W.task(project,{'id':ident,'title':'Public '+ident,'goal':'Exact purpose Ω '+ident,**kw},root)


def row_wire(root,row):
 return W.read(row['namespace'],row['planning_read']['payload'],root)['actions']['planning']['http']['payload']


def retain(root,name,value):
 (root/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2))


def test_emitted_catalogue_and_planning_owner_sample(tmp_path):
 root=tmp_path;(root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'general','project_dir':'p'}]}));(root/'p').mkdir()
 seed(root,'p','prerequisite');seed(root,'p','dependent',depends_on=['prerequisite']);seed(root,'orphan','unregistered')
 initial=W.read('',{'view':'catalogue'},root)
 row=next(x for x in initial['rows'] if x['id']=='unregistered');wire=copy.deepcopy(row_wire(root,row));wire['planning'].update(priority=7,order=-2,deferred=True,reason='Await useful publication checkpoint.')
 result=W.task('orphan',wire,root);read=W.read('orphan',result['read']['payload']|{'namespace':'orphan'},root)
 assert result['effect']=='RECORDED' and read['original_request']==wire
 assert result['current']['planning']['deferred'] is True and row['registered'] is False
 retain(root,'emitted',{'initial':initial,'wire':wire,'saved':result,'request':read,'current':W.read('',{'view':'catalogue'},root)})


def test_complete_193_all_namespace_search_filters_and_pinned_paging(tmp_path):
 root=tmp_path;registered=[f'p{n}' for n in range(10)]
 (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':p,'kind':'general','project_dir':p} for p in registered]}))
 for p in registered:(root/p).mkdir()
 namespaces=registered+['orphan-a','orphan-b','orphan-c']
 for n in range(193):
  p=registered[n%10] if n<188 else namespaces[10+(n-188)%3]
  seed(root,p,f'w{n}',goal='Secret-free unique goal needle Ω' if n==192 else 'Public purpose')
 query={'view':'catalogue','limit':100};ids=[];pages=[];page_bytes=[]
 while True:
  page=W.read('',query,root);pages.append(page);page_bytes.append(len(json.dumps(page,ensure_ascii=False).encode()));ids += [r['qualified_id'] for r in page['rows']]
  assert len(json.dumps(page,ensure_ascii=False).encode())<=B.CAP
  nxt=page['pagination']['next_read']
  if not nxt:break
  query=nxt['payload']
 assert len(ids)==193 and len(set(ids))==193
 assert pages[0]['coverage']=={'total_work':193,'matching_work':193,'namespaces':13,'registered_work':188}
 found=W.read('',{'view':'catalogue','q':'unique goal needle'},root);assert len(found['rows'])==1 and not found['rows'][0]['registered']
 first=found['rows'][0];change=copy.deepcopy(row_wire(root,first));change['planning'].update(deferred=True,reason='Hold for explicit author commission.')
 W.task(first['namespace'],change,root)
 assert W.read('',{'view':'catalogue','planning_filter':'deferred'},root)['coverage']['matching_work']==1
 assert W.read('',{'view':'catalogue','lifecycle':'open','readiness':'READY'},root)['coverage']['matching_work']==193
 with pytest.raises(W.WorkConflict):W.read('',pages[0]['pagination']['next_read']['payload'],root)
 retain(root,'complete-coverage',{'pages':len(pages),'page_bytes':page_bytes,'response_bytes':sum(page_bytes),'all_ids':ids,'first':pages[0],'search':found})


def test_planning_replay_conflict_and_no_completion_or_scope_rewrite(tmp_path):
 root=tmp_path;seed(root,'p','a');proof=root/'public.txt';proof.write_text('public evidence Ω')
 r=W.read('p',{'view':'detail','id':'a'},root);status=r['allowed_actions']['task_status']['payload']
 W.transition('p',{**status,'status':'done','evidence':['public.txt']},root)
 before=W._tasks('p',root)['a'];resolved=W._resolved_tasks({'a':before},root)[0];identity=W._completion_identity(before,{'a':before},{})
 wire=copy.deepcopy(W.read('p',{'view':'detail','id':'a'},root)['allowed_actions']['planning']['http']['payload']);wire['planning'].update(priority=100,deferred=True,reason='Planning only, already done.')
 saved=W.task('p',wire,root);after=W._tasks('p',root)['a'];effective=W._resolved_tasks({'a':after},root)[0]
 assert W._task_revision(before)==W._task_revision(after) and W._standing_revision(before)==W._standing_revision(after)
 assert identity==W._completion_identity(after,{'a':after},{}) and resolved['currentness']==effective['currentness'] and effective['status']=='done'
 newer=copy.deepcopy(saved['current']['actions']['planning']['http']['payload']);newer['planning']['priority']=50;W.task('p',newer,root)
 ledger=W._ledger(root).read_bytes();replay=W.task('p',wire,root);assert replay['replayed'] and replay['receipt']==saved['receipt'] and replay['current']['planning']['priority']==50 and ledger==W._ledger(root).read_bytes()
 with pytest.raises(ValueError,match='another planning intent'):W.task('p',{**wire,'planning':{**wire['planning'],'priority':99}},root)
 stale={**wire,'request_id':'stale-planning-request'};refused=W.task('p',stale,root);assert refused['effect']=='NOT_ADMITTED' and refused['terminal']
 assert W.read('p',refused['read']['payload'],root)['intent_digest']==refused['intent_digest']
 assert W._tasks('p',root)['a']['planning']['priority']==50
 retain(root,'custody-proof',{'saved':saved,'replay':replay,'refused':refused,'currentness':effective['currentness']})


def test_lost_ack_partial_storage_and_detached_request_custody(tmp_path,monkeypatch):
 root=tmp_path;seed(root,'p','a');wire=W.read('p',{'view':'detail','id':'a'},root)['allowed_actions']['planning']['http']['payload']
 original=W._append
 def lost(*args,**kw):
  original(*args,**kw);raise OSError('public post-publication acknowledgement loss')
 monkeypatch.setattr(W,'_append',lost);saved=W.task('p',wire,root);assert saved['effect']=='RECORDED'
 saved['original_request']['planning']['priority']=999
 held=B.inspect_request('p','a',wire['request_id'],root);assert held['original_request']['planning']['priority']==0
 monkeypatch.setattr(W,'_append',original)
 with W._ledger(root).open('a') as f:f.write('{"truncated":')
 assert B.inspect_request('p','a','not-recorded-request',root)['effect']=='UNKNOWN'
 retain(root,'storage-proof',{'lost_ack_recovered':held})


def test_preference_constraints_legacy_order_and_public_http_native_sdk(tmp_path,monkeypatch):
 from laplace import sdk
 from laplace.native import tools
 from laplace.web import project_work_surface as H
 root=tmp_path;seed(root,'p','a');seed(root,'p','b',depends_on=['a']);seed(root,'p','c')
 before=W.read('',{'view':'catalogue'},root);assert [r['id'] for r in before['rows']]==['a','b','c']
 wire=row_wire(root,next(r for r in before['rows'] if r['id']=='b'));wire['planning']['priority']=100
 result=sdk.work_plan('p',wire,root=root);assert result['effect']=='RECORDED'
 page=sdk.work_catalogue(root=root);ids=[r['id'] for r in page['rows']];assert ids.index('a')<ids.index('b')
 native=tools.execute(root,'p','work','project',{'view':'catalogue','q':'Exact purpose'})
 code,_,body=H.handle('/work/state',{'view':['catalogue'],'q':['Exact purpose']},'GET',repo_root=root);assert code==200
 assert [r['qualified_id'] for r in native['rows']]==[r['qualified_id'] for r in json.loads(body)['rows']]
 second=row_wire(root,next(r for r in native['rows'] if r['id']=='c'))
 code,_,body=H.handle('/work/task',{},'POST',json.dumps(second).encode(),repo_root=root);assert code==201 and json.loads(body)['effect']=='RECORDED'
 third=copy.deepcopy(W.read('p',{'view':'detail','id':'a'},root)['allowed_actions']['planning']['http']['payload'])
 actual=tools.execute(root,'p','work','task',{k:v for k,v in third.items() if k!='project'});assert actual['effect']=='RECORDED'
 with pytest.raises(ValueError,match='Review role'):tools.execute(root,'p','review','task',{k:v for k,v in third.items() if k!='project'})
 assert not tools.execute(root,'p','review','project',{'view':'planning','id':'a'})['actions']['planning']['permitted']
 review_request=tools.execute(root,'p','review','project',actual['read']['payload']);assert not review_request['current']['actions']['planning']['permitted']
 seed(root,'orphan','other');scoped=tools.execute(root,'p','work','project',{'view':'catalogue'})
 assert all(r['namespace']=='p' for r in scoped['rows'])
 assert next(r for r in sdk.work_catalogue(root=root)['rows'] if r['namespace']=='orphan')['planning_read']
 retain(root,'parity-proof',{'native':native,'http':json.loads(body),'native_write':actual})


def test_current_review_filters_and_planning_history_do_not_reopen_completion(tmp_path):
 root=tmp_path;seed(root,'p','done');proof=root/'proof.txt';proof.write_text('public original')
 d=W.read('p',{'view':'detail','id':'done'},root);W.transition('p',{**d['allowed_actions']['task_status']['payload'],'status':'done','evidence':['proof.txt']},root)
 assert W.read('',{'view':'catalogue','lifecycle':'done','currentness':'CURRENT'},root)['coverage']['matching_work']==1
 proof.write_text('public changed')
 observed=W.read('',{'view':'catalogue','lifecycle':'done','currentness':'REVIEW_REQUIRED'},root);assert observed['coverage']['matching_work']==1
 r=observed['rows'][0];wire=row_wire(root,r);wire['planning'].update(deferred=True,reason='')
 refused=W.task('p',wire,root);assert refused['effect']=='NOT_ADMITTED' and refused['original_request']==wire
 fresh=refused['current']['actions']['planning']['http']['payload'];fresh['planning'].update(priority=5,reason='Review exact evidence only.')
 W.task('p',fresh,root)
 h=W.read('p',{'view':'history','id':'done'},root);assert [e['record'] for e in h['entries']][-2:]==['planning','planning']
 assert W.read('p',h['entries'][-1]['read']['payload'],root)['effect']=='RECORDED'
 final=W.read('',{'view':'catalogue','lifecycle':'done','currentness':'REVIEW_REQUIRED'},root);assert final['coverage']['matching_work']==1
 retain(root,'review-and-history-proof',{'observed':observed,'refused':refused,'history':h,'final':final})


def test_two_concurrent_planning_decisions_have_one_guard_winner(tmp_path):
 from concurrent.futures import ThreadPoolExecutor
 root=tmp_path;seed(root,'orphan','a');wire=row_wire(root,W.read('',{'view':'catalogue'},root)['rows'][0])
 other=copy.deepcopy(wire);other['request_id']='separate-planning-request';other['planning']['priority']=8
 with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda p:W.task('orphan',p,root),[wire,other]))
 assert sorted(r['effect'] for r in results)==['NOT_ADMITTED','RECORDED']
 assert all(B.inspect_request('orphan','a',r['request_id'],root)['terminal'] for r in results)
 retain(root,'concurrent-proof',results)


def test_help_contract_and_bounded_catalogue_metadata(tmp_path):
 from laplace.native import declarations as D
 from laplace.writing.schemas import SCHEMAS
 from jsonschema import Draft202012Validator
 assert len(json.dumps(D.help_areas('book')).encode())<32768
 assert all('backlog:'+k in D.CONTROL_DECLARATIONS for k in ['catalogue','filters','inspect','planning','check'])
 assert D.help_areas('book','controls')['view_states']['backlog']
 seed(tmp_path,'orphan','a');row=W.read('',{'view':'catalogue'},tmp_path)['rows'][0]
 payload=W.read('orphan',row['planning_read']['payload'],tmp_path)['actions']['planning']['payload'];assert not list(Draft202012Validator(SCHEMAS['task']).iter_errors(payload))
 retain(tmp_path,'metadata-proof',{'default_help_bytes':len(json.dumps(D.help_areas('book')).encode()),'canonical_help_bytes':len(json.dumps(D.help_areas('book'),sort_keys=True,separators=(',',':')).encode()),'schema_valid':True})
 (tmp_path/'areas.json').write_text(json.dumps(D.help_areas('book'),ensure_ascii=False,indent=1)+'\n')
 (tmp_path/'controls.json').write_text(json.dumps(D.help_areas('book','controls'),ensure_ascii=False,indent=1)+'\n')


def test_project_summary_and_branch_explain_preference_without_status_rewrite(tmp_path):
 root=tmp_path;(root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'general','project_dir':'p'}]}));(root/'p').mkdir()
 seed(root,'p','parent');seed(root,'p','a',parent_work_id='parent');seed(root,'p','b',parent_work_id='parent')
 wire=W.read('p',{'view':'detail','id':'a'},root)['allowed_actions']['planning']['http']['payload'];wire['planning'].update(priority=100,deferred=True,reason='Explicit future intent.')
 W.task('p',wire,root)
 summary=W.read('p',{'view':'summary'},root);assert summary['next']['id']!='a'
 branch=W.read('p',{'view':'branch','id':'parent'},root);assert 'higher priority' in branch['order']['kind']
 assert [x['id'] for x in branch['children']]==['b','a'] and all(x['status']=='ready' for x in branch['children'])
 retain(root,'next-preference-proof',{'summary_next':summary['next']['id'],'branch':branch})


def test_scoped_catalogue_and_focused_planning_no_other_namespace_observation(tmp_path,monkeypatch):
 from laplace.native import tools
 from laplace.web import project_work_surface as H
 root=tmp_path;seed(root,'p','a');seed(root,'orphan','private-target',goal='OTHER_SCOPE_GOAL_SENTINEL')
 scoped=tools.execute(root,'p','work','project',{'view':'catalogue'})
 assert scoped['coverage']['total_work']==1 and scoped['coverage']['namespaces']==1 and all(r['namespace']=='p' for r in scoped['rows'])
 assert 'OTHER_SCOPE_GOAL_SENTINEL' not in json.dumps(scoped) and 'orphan' not in json.dumps(scoped)
 code,_,body=H.handle('/work/state',{'view':['catalogue'],'namespace':['p']},'GET',repo_root=root);assert code==200
 human=json.loads(body);assert scoped['rows']==human['rows'] and scoped['coverage']==human['coverage']
 assert scoped['read']['payload']['namespace']=='p' and scoped['active_read']['payload']['namespace']=='p' and scoped['all_read']['payload']['namespace']=='p'
 assert human['scope_id']==W.read('',{'view':'catalogue'},root)['scope_id']
 assert all('actions' not in r for r in human['rows'])
 focused=tools.execute(root,'p','work','project',human['rows'][0]['planning_read']['payload'])
 assert focused['schema_version']=='laplace.work-planning/1' and focused['actions']['planning']['permitted']
 assert 'current_acceptance' not in focused and 'readiness' not in focused
 original=W._tasks;seen=[]
 def observed(project,*a,**kw):
  seen.append(project);return original(project,*a,**kw)
 monkeypatch.setattr(W,'_tasks',observed)
 for view,extras in [('planning',{}),('planning-request',{'request_id':'other-scope-request'})]:
  with pytest.raises(ValueError,match='outside'):tools.execute(root,'p','work','project',{'view':view,'namespace':'orphan','id':'private-target',**extras})
 assert 'orphan' not in seen
 retain(root,'scope-and-focused-proof',{'native':scoped,'human':human,'focused':focused,'request_metadata_calls':seen})


def test_task_first_owner_default_and_suggested_next_keep_recorded_completion(tmp_path):
 root=tmp_path
 for ident in ['done','ready','deferred','held']:seed(root,'p',ident)
 proof=root/'public-proof.txt';proof.write_text('original public evidence')
 d=W.read('p',{'view':'detail','id':'done'},root);W.transition('p',{**d['allowed_actions']['task_status']['payload'],'status':'done','evidence':['public-proof.txt']},root);proof.write_text('changed public evidence')
 w=W.read('p',{'view':'planning','id':'deferred'},root)['actions']['planning']['http']['payload'];w['planning'].update(deferred=True,reason='Explicit later intention.',priority=1000);W.task('p',w,root)
 h=W.read('p',{'view':'detail','id':'held'},root);W.transition('p',{**h['allowed_actions']['task_status']['payload'],'status':'blocked','summary':'Wait for explicit owner choice.'},root)
 whole=W.read('',{'view':'catalogue'},root);active=W.read('',whole['active_read']['payload'],root)
 assert whole['coverage']['total_work']==4 and active['coverage']['matching_work']==2
 assert {r['id'] for r in active['rows']}=={'ready','held'} and active['suggested_next']['id']=='ready'
 assert 'execution' in active['suggested_next']['qualification']
 historical=W.read('',{'view':'catalogue','lifecycle':'done','currentness':'REVIEW_REQUIRED'},root);assert historical['coverage']['matching_work']==1
 none=W.read('',{**whole['active_read']['payload'],'q':'Public held'},root);assert none['suggested_next']['state']=='NONE'
 focused=W.read('p',active['rows'][0]['planning_read']['payload'],root);assert focused['detail_read']['payload']['view']=='detail'
 retain(root,'task-first-proof',{'whole':whole,'active':active,'historical':historical,'none':none,'focused':focused})


def test_planning_history_counts_are_not_review_phases(tmp_path):
 from laplace.work import project_work_review as R
 root=tmp_path;seed(root,'orphan','history',review_obligations=[{'id':'meaning','scope':'guide','label':'Public meaning','required':False,'independent':False}])
 for priority in [37,60]:
  wire=W.read('orphan',{'view':'planning','id':'history'},root)['actions']['planning']['http']['payload'];wire['planning']['priority']=priority;W.task('orphan',wire,root)
 detail=W.read('orphan',{'view':'detail','id':'history'},root);before=detail['reference']['history']
 assert (before['specification'],before['standing'],before['review_phases'],before['planning'])==(1,0,0,2)
 history=W.read('orphan',{'view':'history','id':'history'},root)
 assert [entry['record'] for entry in history['entries']]==['specification','planning','planning']
 proof=root/'meaning.txt';proof.write_text('Public meaning evidence Ω')
 import hashlib
 R.record('orphan',{'id':'history','phase':'handoff','request_id':'public-history-handoff','expected_work_revision':W._task_revision(W._tasks('orphan',root)['history']),
  'object':{'kind':'guide','aggregate':'public-observation'},'evidence':[{'path':'meaning.txt','sha256':'sha256:'+hashlib.sha256(proof.read_bytes()).hexdigest()}]},root)
 final=W.read('orphan',{'view':'detail','id':'history'},root);after=final['reference']['history']
 assert (after['specification'],after['standing'],after['review_phases'],after['planning'])==(1,0,1,2)
 assert final['reference']['evidence']['review_phases_with_evidence']==1
 assert final['task']['planning']==detail['task']['planning'] and final['task']['status']==detail['task']['status']
 retain(root,'planning-history-counts',{'before':detail['reference'],'history':history,'after':final['reference']})
