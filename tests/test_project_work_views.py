"""Owner-level adversarial work diagnoses and exact guarded mutations; isolated state."""
import hashlib,json
from pathlib import Path
import pytest
from laplace.work import project_work as w
from laplace.web import project_work_surface as http
from laplace.native import tools as writing_tools
from laplace.writing import reads as reads_owner


def make(root,ident,**fields):
 return w.task('p',{'id':ident,'title':ident,'goal':'Prove the authored result',**fields},root)


def detail(root,ident):return w.read('p',{'view':'detail','id':ident},root)


def move(root,ident,status,**fields):
 guards=detail(root,ident)['allowed_actions']['task_status']['payload']
 return w.transition('p',{**guards,'status':status,**fields},root)


def evidence(root):
 (root/'result').write_text('observed result')
 return ['result']


def test_completed_lifecycle_review_and_pending_dependent_readiness_are_distinct(tmp_path):
 make(tmp_path,'producer');make(tmp_path,'pending',depends_on=['producer'])
 assert detail(tmp_path,'pending')['task']['readiness']['status']=='BLOCKED'
 move(tmp_path,'producer','done',evidence=evidence(tmp_path))
 assert detail(tmp_path,'pending')['task']['readiness']['status']=='READY'
 make(tmp_path,'historical',depends_on=['producer'])
 move(tmp_path,'historical','done',evidence=['result'])
 (tmp_path/'result').write_text('Changed evidence.')
 old=detail(tmp_path,'historical')['task']
 assert old['lifecycle']=={'status':'done','completed':True,'closed':True}
 assert old['current_acceptance']['review_required'] and old['readiness']['status']=='CLOSED'
 assert not old['readiness']['satisfies_prerequisites']
 assert detail(tmp_path,'pending')['task']['readiness']['status']=='BLOCKED'
 move(tmp_path,'producer','done',evidence=['result'])
 assert detail(tmp_path,'pending')['task']['readiness']['status']=='READY'
 assert detail(tmp_path,'historical')['task']['current_acceptance']['review_required']
 summary=w.read('p',{'view':'summary'},tmp_path)
 assert summary['counts']['pending']==1 and summary['counts']['completed_review_required']==1
 assert summary['counts']['completed']==2
 assert summary['counts']['recorded_lifecycle']=={'done':2,'open':1}


def test_current_own_receipts_do_not_claim_current_acceptance_with_blocked_prerequisite():
 row={'status':'blocked','recorded_status':'done','blocked_by':['WORK-prerequisite'],
      'currentness':{'status':'CURRENT','reason':'all completion evidence matches its recorded digest'}}
 observed=w._read_facets(row)
 assert row['currentness']['status']=='CURRENT'  # The underlying owner fact is preserved.
 assert observed['lifecycle']['closed'] and observed['readiness']['status']=='CLOSED'
 assert not observed['readiness']['satisfies_prerequisites']
 acceptance=observed['current_acceptance']
 assert acceptance['status']=='REVIEW_REQUIRED' and acceptance['currentness']=='CURRENT'
 assert acceptance['review_required'] and acceptance['blocked_by']==['WORK-prerequisite']
 assert 'WORK-prerequisite' in acceptance['reason']
 assert w.read_counts([{**row,**observed}])['completed_review_required']==1


def test_authored_hold_and_stale_disposition_preserve_reason(tmp_path):
 make(tmp_path,'held')
 old=detail(tmp_path,'held')['allowed_actions']['task_status']['payload']
 move(tmp_path,'held','blocked',summary='Await the author decision about experimental scope')
 current=detail(tmp_path,'held')
 assert current['task']['recorded_status']==current['task']['status']=='blocked'
 assert current['blockers'][0]['kind']=='RECORDED_HOLD'
 assert 'experimental scope' in current['blockers'][0]['message']
 before=w._ledger(tmp_path).read_bytes()
 with pytest.raises(w.WorkConflict) as refusal:
  w.transition('p',{**old,'status':'ready'},tmp_path)
 assert refusal.value.details['field']=='expected_work_status_revision'
 assert w._ledger(tmp_path).read_bytes()==before
 with pytest.raises(ValueError,match='explicit ready'):
  move(tmp_path,'held','done',evidence=evidence(tmp_path))
 move(tmp_path,'held','ready',summary='Author explicitly resumed this scope')
 assert detail(tmp_path,'held')['task']['status']=='ready'


def test_dependency_completion_occurrence_does_not_renew_consumer(tmp_path):
 make(tmp_path,'required');make(tmp_path,'consumer',depends_on=['required'])
 result=evidence(tmp_path)
 move(tmp_path,'required','done',evidence=result)
 move(tmp_path,'consumer','done',evidence=result)
 old=detail(tmp_path,'consumer')['allowed_actions']['task_status']['payload']
 assert detail(tmp_path,'consumer')['task']['status']=='done'
 required=detail(tmp_path,'required')['allowed_actions']['task']['payload']
 w.task('p',{**required,'goal':'Prove a stronger result'},tmp_path)
 move(tmp_path,'required','done',evidence=result)
 consumer=detail(tmp_path,'consumer')
 assert consumer['task']['status']=='blocked'
 assert consumer['blockers'][0]['kind']=='DEPENDENCY_BASIS_CHANGED'
 assert consumer['blockers'][0]['consumed_revision']!=consumer['blockers'][0]['observed_revision']
 before=w._ledger(tmp_path).read_bytes()
 with pytest.raises(w.WorkConflict,match='acceptance changed'):
  w.transition('p',{**old,'status':'done','evidence':result},tmp_path)
 assert w._ledger(tmp_path).read_bytes()==before
 move(tmp_path,'consumer','done',evidence=result)
 assert detail(tmp_path,'consumer')['task']['status']=='done'
 # Reaccepting byte-identical prerequisite output is still a new acceptance occurrence.
 move(tmp_path,'required','done',evidence=result)
 assert detail(tmp_path,'consumer')['task']['status']=='blocked'


def test_native_http_exact_shared_projection_and_off_page_focus(tmp_path,monkeypatch):
 for i in range(7):make(tmp_path,str(i))
 monkeypatch.setattr('laplace.pipeline.authoring.load',lambda *a,**k:pytest.fail('full authoring hydration'))
 query={'view':'summary','limit':2}
 native=writing_tools.execute(tmp_path,'session-project','work','project',{'namespace':'p',**query})
 code,_,raw=http.handle('/work/state',{'project':['p'],'view':['summary'],'limit':['2']},'GET',repo_root=tmp_path)
 assert native['review_read']['http']['url']=='/authoring/proposals?project=session-project'
 assert code==200 and reads_owner.read_output_digest('project',json.loads(raw))==reads_owner.read_output_digest('project',native)
 assert len(native['tasks'])==len(native['ready_ids'])==2 and native['ready_total']==7 and 'ready' not in native
 assert native['next']==native['tasks'][0] and native['ready_ids']==[row['id'] for row in native['tasks']]
 pages=[];response=native
 while True:
  pages.extend(row['id'] for row in response['tasks'])
  continuation=response['pagination']['next_read']
  if not continuation:break
  response=writing_tools.execute(tmp_path,'session-project','work','project',continuation['payload'])
 assert pages==[str(i) for i in range(7)]
 focused=detail(tmp_path,'6')
 assert focused['task']['id']=='6'
 guard=focused['allowed_actions']['task']['payload']
 w.task('p',{**guard,'title':'Changed'},tmp_path)
 with pytest.raises(w.WorkConflict):w.read('p',{'view':'summary','limit':2,'as_of':native['read_cut']['revision'],'offset':2},tmp_path)


def test_three_prerequisites_reverse_impact_and_distinct_containment(tmp_path):
 make(tmp_path,'campaign',kind='campaign')
 for i in range(3):make(tmp_path,str(i),parent_work_id='campaign')
 make(tmp_path,'consumer',depends_on=['0','1','2'],parent_work_id='campaign')
 diagnosis=detail(tmp_path,'consumer')
 assert [b['subject']['id'] for b in diagnosis['blockers']]==['0','1','2']
 assert all(b['clear_when']['requires_current_proof'] for b in diagnosis['blockers'])
 assert detail(tmp_path,'0')['dependants']['items'][0]['id']=='consumer'
 assert detail(tmp_path,'campaign')['task']['status']=='ready'
 graph=w.read('p',{'view':'graph','parent_work_id':'campaign','limit':2},tmp_path)
 kinds=[];nodes=[]
 while True:
  nodes.extend(r['id'] for r in graph['nodes']);kinds.extend(e['kind'] for e in graph['edges'])
  nxt=graph['pagination']['next_read']
  if not nxt:break
  graph=w.read('p',nxt['payload'],tmp_path)
 assert len(nodes)==5 and kinds.count('contains')==4 and kinds.count('requires')==3


def test_changed_literature_basis_reports_ready_current_coverage(tmp_path,monkeypatch):
 result=evidence(tmp_path);make(tmp_path,'literature',kind='literature-acquisition')
 scope={'ready_for_completion':True,'revision':'old','gaps':[],'completion_evidence':result,
        'pagination':{'total':3},'source_revision':'source','bibliography':{}}
 monkeypatch.setattr('laplace.research.literature_support.scope',lambda *a,**k:dict(scope))
 move(tmp_path,'literature','done')
 scope['revision']='new'
 blocker=detail(tmp_path,'literature')['blockers'][0]
 assert blocker['kind']=='LITERATURE_SCOPE_CHANGED'
 assert blocker['consumed_revision']=='old' and blocker['observed_revision']=='new'
 assert blocker['current_coverage_ready'] is True and blocker['gaps']==[]
 assert blocker['read_handles'][0]['operation']=='literature_scope'
 assert 'missing' not in blocker['message'].lower()


def test_namespace_listing_is_metadata_only_and_no_inferred_project(tmp_path,monkeypatch):
 make(tmp_path,'engineering')
 monkeypatch.setattr(w,'_resolved_tasks',lambda *a,**k:pytest.fail('global evidence hydration'))
 out=w.read('',{'view':'namespaces'},tmp_path)
 assert out['items'][0]['id']=='p' and out['items'][0]['registered'] is False
 assert out['items'][0]['read_handle']['payload']['namespace']=='p'
 assert not (tmp_path/'registry_projects.json').exists()


def test_unknown_legacy_and_withdrawal_never_complete_required_work(tmp_path):
 make(tmp_path,'prerequisite');make(tmp_path,'consumer',depends_on=['prerequisite'])
 move(tmp_path,'prerequisite','withdrawn',summary='Author withdrew this experiment; no result accepted')
 assert detail(tmp_path,'prerequisite')['task']['status']=='withdrawn'
 assert detail(tmp_path,'consumer')['task']['status']=='blocked'
 legacy={'id':'legacy','project':'p','status':'done','depends_on':['prerequisite'],
         'evidence_receipts':[{'path':'result','sha256':hashlib.sha256(b'x').hexdigest()}]}
 currency=w._evidence_currentness(legacy,tmp_path,tasks={'prerequisite':w._tasks('p',tmp_path)['prerequisite'],'legacy':legacy})
 assert currency['status']=='STALE' and any(d['kind']=='DEPENDENCY_PROOF_MISSING' for d in currency['diagnoses'])


def test_forward_chain_and_cycle_use_iterative_fold_and_unique_evidence_read(tmp_path,monkeypatch):
 result=tmp_path/'result';result.write_text('shared evidence')
 receipt={'path':'result','sha256':hashlib.sha256(result.read_bytes()).hexdigest()}
 rows={str(i):{'id':str(i),'project':'p','status':'open','title':'Goal','goal':'Condition',
             'depends_on':[str(i+1)] if i<999 else [],'parent_work_id':None} for i in range(1000)}
 original=w._task_revision;calls=[]
 monkeypatch.setattr(w,'_task_revision',lambda r:calls.append(r['id']) or original(r))
 out=w._resolved_tasks(rows,tmp_path)
 assert len(out)==1000 and len(calls)==1000 and out[-1]['status']=='ready'
 assert all(r['status']=='blocked' for r in out[:-1])
 rows['999']['depends_on']=['0']
 assert all(r['status']=='blocked' for r in w._resolved_tasks(rows,tmp_path))
 opened=[];original_open=Path.open
 def observe(p,*a,**k):
  if p==result:opened.append(p)
  return original_open(p,*a,**k)
 monkeypatch.setattr(Path,'open',observe)
 proofs={str(i):{'id':str(i),'project':'p','status':'done','evidence_receipts':[receipt]} for i in range(1000)}
 assert all(r['status']=='done' for r in w._resolved_tasks(proofs,tmp_path))
 assert len(opened)==1


def _saved_failure_and_receipt(row,returned):
 # The saved row is written once, before the answer; the answer then adds the two fields that
 # address that row (its own id cannot be inside it). Every other recovery field is identical.
 receipt_fields={'failure_receipt','failure_read'}
 assert set(returned)-set(row['recovery'])==receipt_fields and not receipt_fields&set(row['recovery'])
 assert {k:v for k,v in returned.items() if k not in receipt_fields}==row['recovery']
 assert returned['failure_receipt']=={'note':'','row_id':row['id']}
 assert returned['failure_read']=={'operation':'author_history','payload':{'id':'activity:journal:'+row['id'],'view':'record'}}


def test_failure_recovery_is_saved_once_before_later_world_changes(tmp_path,monkeypatch):
 from laplace.representation import writing_bodies
 from laplace.writing.records import _fold as records_fold
 original={'ok':False,'operation':'task','error':'Changed input','next_reads':[{'operation':'project','payload':{'view':'detail','id':'old'}}],
           'consumed_read_recovery':{'old':'retained owner proof'}}
 monkeypatch.setattr(writing_tools,'failure_response',lambda *args,**kwargs:original.copy())
 returned=writing_tools.tool_failure(tmp_path,'p','work','task',{},ValueError('Changed input'))
 lines=(tmp_path/records_fold._STORE).read_text().splitlines();assert len(lines)==1   # recorded exactly once
 row=writing_bodies.resolve_fields(json.loads(lines[-1]),tmp_path)
 _saved_failure_and_receipt(row,returned)
 assert row['recovery']=={**original} and row['next_reads']==original['next_reads']
 assert row['consumed_read_recovery']==original['consumed_read_recovery']
 monkeypatch.setattr(writing_tools,'failure_response',lambda *args,**kwargs:pytest.fail('historical reconstruction'))
 assert writing_bodies.resolve_fields(row,tmp_path)['recovery']==original


def test_admitted_provider_settings_come_from_turn_not_mutable_session():
 from laplace.writing import session_reads
 admitted={'provider':'codex','model':'original','effort':'high'}
 turn={'id':'T','session_id':'S','provider_settings':admitted}
 records={'orders':{},'sessions':{'S':{'provider':'claude','model':'later','effort':'low'}}}
 assert session_reads._session_turn_summary(turn,records)['provider_settings']==admitted


def test_existing_legacy_workflow_adapter_never_invents_resume_or_live_activity(tmp_path):
 from laplace.pipeline import workflow
 ident='WORKFLOW-20261006T142944Z-4692b3a3b876'
 directory=tmp_path/'evidence/WORKFLOWS'/ident;directory.mkdir(parents=True)
 (tmp_path/'contract').mkdir()
 result=directory/'returns.json';result.write_text('{"returns":[]}')
 path=result.relative_to(tmp_path).as_posix()
 row={'record':'workflow','id':ident,'phase':'result','status':'PENDING','accepted':False,
      'result_path':path,'result_handle':workflow.digest(result.read_bytes())}
 (tmp_path/workflow.LEDGER).write_text(json.dumps(row)+'\n')
 recent=w.read('',{'view':'workflows'},tmp_path)
 assert recent['workflows'][0]['read_handle']['payload']['run_id']==ident
 exact=w.read('',{'view':'workflows','run_id':ident},tmp_path)
 assert exact['status']=='RECORDED-PENDING' and exact['accepted'] is False
 assert exact['manifest']=='ABSENT' and exact['resume_permitted'] is False
 assert exact['activity'].startswith('UNKNOWN') and exact['continuation']['available'] is False
 result.write_text('{"changed":true}')
 refused=w.read('',{'view':'workflows','run_id':ident},tmp_path)
 assert refused['status']=='REFUSED' and refused['accepted'] is False
 assert 'MISMATCH' in refused['current_return_problems'][0]
 assert not (directory/'run.json').exists()


def test_failure_is_durable_even_if_help_formatter_fails(tmp_path,monkeypatch):
 from laplace.representation import writing_bodies
 from laplace.writing.records import _fold as records_fold
 def unavailable(*args,**kwargs):raise RuntimeError('help metadata unavailable')
 monkeypatch.setattr(writing_tools,'failure_response',unavailable)
 original=w.WorkConflict('Original changed standing','p','held',expected='old',observed='new')
 returned=writing_tools.tool_failure(tmp_path,'p','work','task_status',{'id':'held'},original)
 lines=(tmp_path/records_fold._STORE).read_text().splitlines();assert len(lines)==1   # durable once, formatter failed
 row=writing_bodies.resolve_fields(json.loads(lines[-1]),tmp_path)
 assert row['error']=='Original changed standing'
 _saved_failure_and_receipt(row,returned)
 assert returned['next_reads']==original.details['next_reads']
 assert 'help metadata unavailable' in returned['recovery_unavailable']


def test_unpinned_historical_dependency_keeps_independent_changed_evidence_diagnosis(tmp_path):
 make(tmp_path,'required');move(tmp_path,'required','done',evidence=evidence(tmp_path))
 make(tmp_path,'legacy-consumer',depends_on=['required'])
 pdf=tmp_path/'edition.pdf';pdf.write_bytes(b'new edition')
 old=hashlib.sha256(b'old edition').hexdigest();current=hashlib.sha256(pdf.read_bytes()).hexdigest()
 w._append(tmp_path,{'record':'project-work-transition','kind':'work-order','id':'legacy-consumer','task_id':'legacy-consumer',
   'project':'p','status':'done','ts':'historical','evidence':['edition.pdf'],
   'evidence_receipts':[{'path':'edition.pdf','sha256':old}]})
 original=w._ledger(tmp_path).read_bytes()
 native=writing_tools.execute(tmp_path,'p','work','project',{'view':'detail','id':'legacy-consumer'})
 code,_,body=http.handle('/work/state',{'project':['p'],'view':['detail'],'id':['legacy-consumer']},'GET',repo_root=tmp_path)
 assert native['review_read']['http']['url']=='/authoring/proposals?project=p'
 assert code==200 and reads_owner.read_output_digest('project',json.loads(body))==reads_owner.read_output_digest('project',native)
 assert native['task']['recorded_status']=='done' and native['task']['status']=='blocked'
 diagnoses=native['task']['currentness']['diagnoses']
 assert [d['kind'] for d in diagnoses]==['EVIDENCE_CHANGED','DEPENDENCY_PROOF_MISSING']
 changed,missing=native['blockers']
 assert changed['consumed_revision']==old and changed['observed_revision']==current
 assert changed['subject']['path']=='edition.pdf'
 assert missing['legacy'] is True and missing['basis_status']=='UNPINNED_LEGACY'
 assert missing['consumed_revision'] is None
 assert missing['clear_when']['predicate']=='explicit_guarded_recompletion_with_current_prerequisite_pins'
 assert 'never reconstructed' in missing['clear_when']['historical_consumed_basis']
 assert changed['clear_when']['predicate']=='explicit_completion_on_inspected_current_basis'
 summary=w.read('p',{'view':'summary'},tmp_path)
 row=next(r for r in summary['tasks'] if r['id']=='legacy-consumer')
 # The LIST row carries the primary standing only; the two diagnoses stay with detail.
 assert row['currentness']=={'status':'STALE','kind':'EVIDENCE_CHANGED'}
 assert 'diagnoses' not in row['currentness'] and 'evidence_currentness' not in row and 'evidence' not in row
 assert row['read_handle']['payload']=={'namespace':'p','view':'detail','id':'legacy-consumer'}
 assert w._ledger(tmp_path).read_bytes()==original
 assert 'completion_dependency_basis' not in w._tasks('p',tmp_path)['legacy-consumer']


def test_unpinned_legacy_with_matching_evidence_remains_unverified_without_fabricated_pins(tmp_path):
 make(tmp_path,'required');move(tmp_path,'required','done',evidence=evidence(tmp_path))
 make(tmp_path,'legacy',depends_on=['required'])
 receipt={'path':'result','sha256':hashlib.sha256((tmp_path/'result').read_bytes()).hexdigest()}
 w._append(tmp_path,{'record':'project-work-transition','kind':'work-order','id':'legacy','task_id':'legacy',
                    'project':'p','status':'done','evidence_receipts':[receipt]})
 value=detail(tmp_path,'legacy')
 assert value['task']['recorded_status']=='done' and value['task']['currentness']['status']=='UNKNOWN'
 assert value['task']['currentness']['diagnoses'][0]['status']=='CURRENT'
 assert value['task']['currentness']['diagnoses'][1]['kind']=='DEPENDENCY_PROOF_MISSING'
 assert len(value['blockers'])==1 and value['blockers'][0]['basis_status']=='UNPINNED_LEGACY'
 assert 'completion_dependency_basis' not in w._tasks('p',tmp_path)['legacy']
 with pytest.raises(w.WorkConflict):
  w.transition('p',{'id':'legacy','status':'done','evidence':['result']},tmp_path)


def test_queue_filters_before_paging_and_retains_exact_request_anchor_and_goal(tmp_path,monkeypatch):
 source=tmp_path/'p/manuscript';source.mkdir(parents=True)
 (source/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nSelected sentence.\n\\end{document}\n')
 (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','project_dir':'p','tex_root':'p/manuscript',
   'manifest':{'document':{'root':'p/manuscript/main.tex'}}}]}))
 for i in range(55):make(tmp_path,'ordinary-'+str(i))
 anchor={'file':'main.tex','line_start':3,'line_end':3,'quote':'Selected sentence.'}
 goal=('Preserve this exact queued request. '*15).strip()
 for i in range(2):make(tmp_path,'request-'+str(i),kind='session-request',goal=goal,anchor=anchor)
 monkeypatch.setattr('laplace.pipeline.authoring.load',lambda *a,**k:pytest.fail('queue authoring hydration'))
 first=writing_tools.execute(tmp_path,'p','work','project',{'view':'queue','limit':1})
 code,_,raw=http.handle('/work/state',{'project':['p'],'view':['queue'],'limit':['1']},'GET',repo_root=tmp_path)
 assert first['review_read']['http']['url']=='/authoring/proposals?project=p'
 assert code==200 and reads_owner.read_output_digest('project',json.loads(raw))==reads_owner.read_output_digest('project',first)
 assert first['pagination']['total']==2 and first['tasks'][0]['id']=='request-0'
 assert first['tasks'][0]['goal']==goal and first['tasks'][0]['anchor']==anchor
 second=writing_tools.execute(tmp_path,'p','work','project',first['pagination']['next_read']['payload'])
 assert second['tasks'][0]['id']=='request-1' and second['pagination']['next_read'] is None
 assert second['tasks'][0]['goal']==goal and second['tasks'][0]['anchor']==anchor
 guards=second['tasks'][0]['allowed_actions']['task_status']['payload']
 assert w.transition('p',{**guards,'status':'cancelled'},tmp_path)['status']=='cancelled'
 with pytest.raises(w.WorkConflict) as refusal:
  w.read('p',first['pagination']['next_read']['payload'],tmp_path)
 assert refusal.value.details['next_reads'][0]['payload']['view']=='queue'
 assert 'as_of' not in refusal.value.details['next_reads'][0]['payload']
 assert (source/'main.tex').read_text().splitlines()[2]=='Selected sentence.'


def test_work_read_and_continuation_ignore_other_project_appends(tmp_path):
 make(tmp_path,'one');make(tmp_path,'two')
 first=w.read('p',{'view':'summary','limit':1},tmp_path)
 digest=reads_owner.read_output_digest('project',first)
 w.task('other',{'id':'elsewhere','title':'Other work','goal':'Unrelated work'},tmp_path)
 again=w.read('p',{'view':'summary','limit':1},tmp_path)
 assert again==first
 assert reads_owner.read_output_digest('project',again)==digest
 second=w.read('p',first['pagination']['next_read']['payload'],tmp_path)
 assert second['tasks'][0]['id']=='two'
 make(tmp_path,'three')
 with pytest.raises(w.WorkConflict):
  w.read('p',first['pagination']['next_read']['payload'],tmp_path)


def test_registered_repository_evidence_is_shared_unbound_observation_without_handle_body_reads(tmp_path, monkeypatch):
 from laplace.projects import library as projects, writing_sources
 from urllib.parse import urlsplit, parse_qs
 project=projects.create({'name':'consumer','title':'Consumer','kind':'general'},tmp_path)[1]['project']
 source=tmp_path/'current-criteria.md';source.write_text('π criterion and historical scope')
 original=source.read_bytes();make_row={'id':'campaign','title':'Campaign','goal':'Continue current work','evidence':[source.name]}
 w.task(project,make_row,tmp_path)
 # Building Work evidence handles must neither hash nor hydrate the source body.
 with monkeypatch.context() as scope:
  scope.setattr(writing_sources,'_identity',lambda *_:pytest.fail('body hashing while constructing a handle'))
  scope.setattr(writing_sources,'execute',lambda *_:pytest.fail('body read while constructing a handle'))
  work=w.read(project,{'view':'detail','id':'campaign','limit':1},tmp_path)
 handle=work['task']['evidence_reads'][0]
 assert handle['available'] and handle['consumed_revision'] is None
 assert handle['payload']['target']=={'owner':'repository','repository':'laplace','path':source.name}
 native=writing_tools.execute(tmp_path,project,'work',handle['operation'],handle['payload'])
 parts=urlsplit(handle['http']['url'])
 code,_,raw=projects.handle(parts.path,parse_qs(parts.query),'GET',b'',repo_root=tmp_path)
 assert code==200 and native==json.loads(raw)
 assert native['currentness']=='UNBOUND' and native['consumed_revision'] is None
 assert native['current_revision']==hashlib.sha256(original).hexdigest()
 assert native['owner_result']['content']=='π criterion and historical scope'
 assert native['write_permission'] is False and source.read_bytes()==original
 assert work['task']['currentness']['status']=='NOT_REQUIRED'
 assert not projects.material_references(project,tmp_path)['references']


def test_nested_repository_work_coordinate_uses_unique_workspace_read_route(tmp_path,monkeypatch):
 from laplace.projects import library as projects, writing_sources
 from urllib.parse import urlsplit,parse_qs
 project=projects.create({'name':'consumer','title':'Consumer','kind':'general'},tmp_path)[1]['project']
 source=tmp_path/'package/src/basis.py';source.parent.mkdir(parents=True)
 source.write_text('Shared nested π basis\n');original=source.read_bytes()
 config=tmp_path/'profiles/writing_sources.json';config.parent.mkdir(exist_ok=True)
 config.write_text(json.dumps({'repositories':{'nested-package':'package','checkout-read':'.'}}))
 coordinate=source.relative_to(tmp_path).as_posix()
 w.task(project,{'id':'campaign','title':'Campaign','goal':'Inspect exact recorded basis','evidence':[coordinate]},tmp_path)
 ledger=w._ledger(tmp_path).read_bytes()
 original_read=Path.read_bytes
 def observed_read(path):
  if path.resolve()==source.resolve():pytest.fail('body lookup while constructing a read route')
  return original_read(path)
 with monkeypatch.context() as scope:
  scope.setattr(Path,'read_bytes',observed_read)
  scope.setattr(writing_sources,'_identity',lambda *_:pytest.fail('hash lookup while constructing a read route'))
  handle=w.read(project,{'view':'detail','id':'campaign'},tmp_path)['task']['evidence_reads'][0]
 assert handle['available'] and handle['payload']['target']=={
  'owner':'repository','repository':'checkout-read','path':coordinate}
 native=writing_tools.execute(tmp_path,project,'work',handle['operation'],handle['payload'])
 parts=urlsplit(handle['http']['url'])
 code,_,raw=projects.handle(parts.path,parse_qs(parts.query),'GET',b'',repo_root=tmp_path)
 assert code==200 and native==json.loads(raw)
 explicit=writing_sources.execute(tmp_path,{'action':'read','repository':'nested-package','path':'src/basis.py','limit':16000})
 assert native['owner_result']['content']==explicit['content']==original.decode()
 assert native['current_revision']==explicit['source']['sha256']==hashlib.sha256(original).hexdigest()
 assert native['currentness']=='UNBOUND' and native['write_permission'] is False
 assert w._ledger(tmp_path).read_bytes()==ledger and source.read_bytes()==original


def test_workspace_read_route_preserves_internal_symlink_and_absolute_ambiguity(tmp_path):
 from laplace.projects import writing_sources
 source=tmp_path/'package/basis.md';source.parent.mkdir();source.write_text('Internal linked basis')
 link=tmp_path/'linked.md';link.symlink_to(source)
 config=tmp_path/'profiles/writing_sources.json';config.parent.mkdir()
 config.write_text(json.dumps({'repositories':{'nested-route':'package','workspace-route':'.'}}))
 target=writing_sources.target_for_path(tmp_path,link.name)
 assert target=={'owner':'repository','repository':'workspace-route','path':link.name}
 explicit={'action':'read','repository':'workspace-route','path':link.name}
 assert writing_sources.execute(tmp_path,explicit)['content']==source.read_text()
 with pytest.raises(ValueError,match='ambiguous'):
  writing_sources.target_for_path(tmp_path,str(source))


@pytest.mark.parametrize('case',['undeclared','ambiguous','unavailable','symlink','traversal'])
def test_repository_evidence_refuses_wrong_owners_and_escapes(tmp_path,case):
 from laplace.projects import library as projects
 project=projects.create({'name':'consumer','title':'Consumer','kind':'general'},tmp_path)[1]['project']
 config=tmp_path/'profiles/writing_sources.json';config.parent.mkdir(exist_ok=True)
 source=tmp_path/'evidence.md';source.write_text('Existing basis')
 path=source.name
 if case=='undeclared':mapping={'other':'other'}
 elif case=='ambiguous':mapping={'one':'.','two':'.'}
 elif case=='unavailable':mapping={'absent':'absent'};path='absent/evidence.md'
 elif case=='symlink':
  outside=tmp_path.parent/(tmp_path.name+'-external.txt');outside.write_text('Must not read')
  source.unlink();source.symlink_to(outside);mapping={'declared':'.'}
 else:mapping={'declared':'.'};path='../escape.md'
 config.write_text(json.dumps({'repositories':mapping}))
 w.task(project,{'id':'campaign','title':'Campaign','goal':'Continue','evidence':[path]},tmp_path)
 handles=w.read(project,{'view':'detail','id':'campaign'},tmp_path)['task']['evidence_reads']
 assert len(handles)==1 and handles[0]['available'] is False
 assert 'http' not in handles[0] and 'operation' not in handles[0]
 assert handles[0]['capability_gap']


def test_project_artifact_evidence_keeps_its_existing_pinned_route(tmp_path):
 from laplace.projects import library as projects
 project=projects.create({'name':'consumer','title':'Consumer','kind':'general'},tmp_path)[1]['project']
 local=tmp_path/'writing_projects/consumer/notes.md';local.write_text('Inspected result')
 w.task(project,{'id':'done','title':'Done','goal':'Result'},tmp_path)
 basis=w.read(project,{'view':'detail','id':'done'},tmp_path)['allowed_actions']['task_status']['payload']
 w.transition(project,{**basis,'status':'done','evidence':[local.relative_to(tmp_path).as_posix()]},tmp_path)
 handle=w.read(project,{'view':'detail','id':'done'},tmp_path)['task']['evidence_reads'][0]
 assert handle['operation']=='read_artifact' and handle['http']['url'].startswith('/research/artifact?')
 assert 'expected_sha256='+hashlib.sha256(local.read_bytes()).hexdigest() in handle['http']['url']


def test_configured_external_repository_evidence_keeps_declared_alias(tmp_path):
 from laplace.projects import library as projects
 project=projects.create({'name':'consumer','title':'Consumer','kind':'general'},tmp_path)[1]['project']
 external=tmp_path.parent/(tmp_path.name+'-public-source');external.mkdir()
 source=external/'criteria.md';source.write_text('Declared external basis')
 config=tmp_path/'profiles/writing_sources.json';config.parent.mkdir(exist_ok=True)
 config.write_text(json.dumps({'repositories':{'external-public':str(external)}}))
 w.task(project,{'id':'campaign','title':'Campaign','goal':'Continue','evidence':[str(source)]},tmp_path)
 handle=w.read(project,{'view':'detail','id':'campaign'},tmp_path)['task']['evidence_reads'][0]
 assert handle['available'] and handle['payload']['target']=={'owner':'repository','repository':'external-public','path':'criteria.md'}
 read=writing_tools.execute(tmp_path,project,'work',handle['operation'],handle['payload'])
 assert read['owner_result']['content']=='Declared external basis' and read['currentness']=='UNBOUND'


def test_repository_preview_observes_changed_bytes_without_renewing_historical_completion(tmp_path):
 from laplace.projects import library as projects
 project=projects.create({'name':'consumer','title':'Consumer','kind':'general'},tmp_path)[1]['project']
 source=tmp_path/'result.md';source.write_text('Accepted historical result')
 w.task(project,{'id':'done','title':'Done','goal':'Result'},tmp_path)
 guards=w.read(project,{'view':'detail','id':'done'},tmp_path)['allowed_actions']['task_status']['payload']
 w.transition(project,{**guards,'status':'done','evidence':[source.name]},tmp_path)
 original=w._ledger(tmp_path).read_bytes();consumed=hashlib.sha256(source.read_bytes()).hexdigest()
 source.write_text('Changed current result')
 current=w.read(project,{'view':'detail','id':'done'},tmp_path)
 handle=current['task']['evidence_reads'][0]
 assert current['task']['status']=='blocked' and handle['consumed_revision']==consumed
 read=writing_tools.execute(tmp_path,project,'work',handle['operation'],handle['payload'])
 assert read['currentness']=='UNBOUND' and read['current_revision']!=consumed
 assert w._ledger(tmp_path).read_bytes()==original


# ---- C1a: shared Work owner contract — LIST projection, paging, fold cache, blockers ----

def _synthetic_rows(root,count,*,evidence_files=2):
 """Bounded parametric fixture: `count` Work rows with long goals and evidence paths.

 Rows are appended through the owner's own append so receipts, stamps and the fold
 cache behave as in production; nothing is copied from a real project."""
 for index in range(evidence_files):
  (root/f'evidence-{index}.txt').write_text('synthetic evidence %d\n'%index*40)
 for index in range(count):
  w._append(root,{'record':'project-work','kind':'work-order','id':f'WORK-{index:04d}','task_id':f'WORK-{index:04d}','project':'p',
   'title':f'Synthetic work {index}','goal':('Prove the authored result in full detail. '*20),'status':'open','task_kind':'execution',
   'parent_work_id':f'WORK-{index-1:04d}' if index%7==1 else None,'depends_on':[f'WORK-{index-2:04d}'] if index%5==2 else [],
   'section_ids':[],'evidence':[f'evidence-{index%evidence_files}.txt'],'origin':'synthetic','ts':'2026-10-12T00:00:00Z'})


def test_list_projection_is_bounded_per_row_and_continuation_pages_carry_no_envelope(tmp_path):
 w._FOLD_CACHE.clear();_synthetic_rows(tmp_path,300)
 first=w.read('p',{'view':'summary','limit':100},tmp_path)
 rows=first['tasks'];assert len(rows)==100 and first['pagination']['total']==300
 # LIST rows: identity, structure, standing facets, two pins and the detail handle; no bodies.
 for row in rows:
  assert not {'goal','evidence','evidence_receipts','completion_work_basis','work_revision','work_scope_revision','work_status_revision','dependency_revision','completion_revision','evidence_currentness','summary'}&set(row)
  assert set(row['lifecycle'])<={'status','completed','closed'} and set(row['readiness'])<={'status','blocked_by'}
  assert set(row['current_acceptance'])<={'status','review_required','kind'} and set(row['currentness'])<={'status','kind'}
  assert row['read_handle']['http']['url'].startswith('/work/state?') and row['qualified_id']=='p::'+row['id']
 per_row=len(json.dumps(rows).encode())/len(rows)
 # Measured: about 0.85 KB per synthetic row (about 1.26 KB on the large real project, where
 # titles, prerequisite lists and ids are longer; amended line 1.3 KB) against about 4.5 KB
 # per FULL row before C1a.
 assert per_row<=1100,per_row
 # Linear in rows: a page of 100 costs about the same per row as a page of 10.
 small=w.read('p',{'view':'summary','limit':10},tmp_path)['tasks']
 assert abs(len(json.dumps(small).encode())/len(small)-per_row)<per_row*0.25
 # Page one carries the project envelope once; continuation pages repeat only rows, counts and the cut.
 assert {'framing','form','style','project_protocol','ready_ids','next','counts','read_cut'}<=set(first) and 'ready' not in first
 second=w.read('p',first['pagination']['next_read']['payload'],tmp_path)
 assert second['continuation'] is True and second['pagination']['offset']==100 and len(second['tasks'])==100
 assert not {'framing','form','style','project_protocol','ready_ids','next'}&set(second)
 assert second['counts']==first['counts'] and second['read_cut']==first['read_cut']
 # The graph delivers the same LIST row shape for nodes.
 graph=w.read('p',{'view':'graph','limit':50},tmp_path)
 assert graph['pagination']['total']==300 and 'goal' not in graph['nodes'][0] and 'lifecycle' in graph['nodes'][0]
 # Detail and queue keep the FULL projection: bodies, pins and guarded actions live there.
 focused=w.read('p',{'view':'detail','id':'WORK-0002'},tmp_path)
 full=focused['task']
 assert full['goal'].startswith('Prove') and full['evidence']==['evidence-0.txt'] and 'work_revision' in full
 assert full['work_scope_revision'].startswith('sha256:') and full['dependency_revision'].startswith('sha256:')
 assert focused['allowed_actions']['task_status']['payload']['expected_work_scope_revision']==full['work_scope_revision']


def test_ledger_fold_is_served_from_stat_identity_and_advanced_by_append(tmp_path,monkeypatch):
 w._FOLD_CACHE.clear()
 make(tmp_path,'one');make(tmp_path,'two')
 first=w.read('p',{'view':'summary'},tmp_path)
 state=w.fold_cache_state(tmp_path);assert state and state['rows']==2 and state['projects']==['p']
 # Same stat identity: the ledger text is never parsed again.
 monkeypatch.setattr(w,'_fold_rows',lambda text:pytest.fail('the fold was reparsed although the ledger stat identity is unchanged'))
 again=w.read('p',{'view':'summary'},tmp_path)
 assert again==first and w.fold_cache_state(tmp_path)['stamp']==state['stamp']
 # The owner's own append advances the cache in place: one more row, a new stamp, no reparse.
 make(tmp_path,'three')
 advanced=w.fold_cache_state(tmp_path);assert advanced['rows']==3 and advanced['stamp']!=state['stamp']
 assert set(w._tasks('p',tmp_path))=={'one','two','three'}
 # A fresh copy per call: annotating a returned task never changes the fold.
 w._tasks('p',tmp_path)['one']['title']='mutated by a caller'
 assert w._tasks('p',tmp_path)['one']['title']=='one'
 # Another writer (another process) changes the stat identity; the next read refolds.
 monkeypatch.undo()
 with w._ledger(tmp_path).open('a',encoding='utf8') as handle:
  handle.write(json.dumps({'record':'project-work','kind':'work-order','id':'external','task_id':'external','project':'p','title':'External','goal':'g','status':'open'})+'\n')
 assert 'external' in w._tasks('p',tmp_path) and w.fold_cache_state(tmp_path)['rows']==4


def test_evidence_digest_reuse_observes_a_changed_file_by_stat_identity(tmp_path):
 w._DIGEST_CACHE.clear()
 make(tmp_path,'proved');move(tmp_path,'proved','done',evidence=evidence(tmp_path))
 assert detail(tmp_path,'proved')['task']['currentness']['status']=='CURRENT'
 (tmp_path/'result').write_text('observed result, revised')
 changed=detail(tmp_path,'proved')['task']['currentness']
 assert changed['status']=='STALE' and changed['kind']=='EVIDENCE_CHANGED'


def test_blockers_name_the_subject_title_standing_relation_and_kinded_actions(tmp_path):
 make(tmp_path,'producer',title='Measure the spectrum');make(tmp_path,'consumer',depends_on=['producer'])
 waiting,=detail(tmp_path,'consumer')['blockers']
 assert waiting['kind']=='PREREQUISITE_NOT_COMPLETE' and waiting['relation']=='prerequisite'
 assert waiting['sentence']=='Waiting on Measure the spectrum, which is ready.'
 assert waiting['subject']['title']=='Measure the spectrum' and waiting['subject']['standing']['status']=='ready'
 assert waiting['subject']['standing']['lifecycle']['status']=='open' and waiting['subject']['standing']['readiness']['status']=='READY'
 assert 'producer' not in waiting['sentence'] and waiting['message']=='Prerequisite producer is ready.'
 assert [a['kind'] for a in waiting['next_actions']]==['inspect-prerequisite']
 # A held Work's own subject carries its title and standing too, and the hold is the relation.
 make(tmp_path,'held',title='Write the discussion');move(tmp_path,'held','blocked',summary='Awaiting the referee report.')
 hold,=detail(tmp_path,'held')['blockers']
 assert hold['kind']=='RECORDED_HOLD' and hold['relation']=='hold' and hold['sentence']=='Held: Awaiting the referee report.'
 assert hold['subject']['title']=='Write the discussion' and hold['subject']['standing']['status']=='blocked'
 assert hold['next_actions'][0]['kind']=='prepare' and hold['next_actions'][0]['operation']=='task_status'
 # The native reader receives the same fields through the same owner.
 native=writing_tools.execute(tmp_path,'p','work','project',{'view':'detail','id':'consumer'})
 assert native['blockers'][0]['subject']['title']=='Measure the spectrum' and native['blockers'][0]['relation']=='prerequisite'


# ---- C1a repair: nested aliasing, finite retention, publication under concurrency ----

def test_returned_rows_never_alias_the_fold_nested_values_included(tmp_path):
 w._FOLD_CACHE.clear()
 make(tmp_path,'base');make(tmp_path,'consumer',depends_on=['base'],section_ids=[])
 # Owner copies: nested lists and dicts belong to the caller.
 owned=w._tasks('p',tmp_path);owned['consumer']['depends_on'].append('planted');owned['consumer']['nested']={'x':1}
 assert w._tasks('p',tmp_path)['consumer']['depends_on']==['base'] and 'nested' not in w._tasks('p',tmp_path)['consumer']
 # HTTP page: mutate nested values of a delivered row and a delivered facet.
 code,_,body=http.handle('/work/state',{'project':['p'],'view':['summary']},'GET',repo_root=tmp_path)
 page=json.loads(body);row=next(r for r in page['tasks'] if r['id']=='consumer')
 row['depends_on'].append('planted');row['readiness']['blocked_by'].append('planted');row['lifecycle']['status']='forged'
 # Native result: same owner, same guarantee, including the resolved detail.
 native=writing_tools.execute(tmp_path,'p','work','project',{'view':'detail','id':'consumer'})
 native['task']['depends_on'].append('planted');native['blockers'][0]['subject']['standing']['lifecycle']['status']='forged'
 again=w.read('p',{'view':'summary'},tmp_path);clean=next(r for r in again['tasks'] if r['id']=='consumer')
 assert clean['depends_on']==['base'] and clean['readiness']['blocked_by']==['base'] and clean['lifecycle']['status']=='open'
 assert detail(tmp_path,'consumer')['blockers'][0]['subject']['standing']['lifecycle']['status']=='open'
 # The published rows themselves are an immutable sequence.
 assert isinstance(w._rows(tmp_path),tuple)


def test_fold_cache_evicts_least_recently_used_ledgers_and_never_retains_an_oversize_one(tmp_path,monkeypatch):
 w._FOLD_CACHE.clear();monkeypatch.setattr(w,'FOLD_CACHE_MAX_ENTRIES',2)
 roots=[]
 for name in ('a','b','c'):
  root=tmp_path/name;root.mkdir();roots.append(root);make(root,'one-'+name)
 for root in roots:assert set(w._tasks('p',root))=={'one-'+root.name}
 assert len(w._FOLD_CACHE)==2 and w.fold_cache_state(roots[0]) is None   # least recently used ledger evicted
 assert set(w._tasks('p',roots[0]))=={'one-a'}                           # eviction costs a re-read, not correctness
 assert w.fold_cache_state(roots[1]) is None and w.fold_cache_state(roots[0])['entries']==2
 # An oversize ledger is parsed complete on every read and never retained.
 monkeypatch.setattr(w,'FOLD_CACHE_MAX_LEDGER_BYTES',64);w._FOLD_CACHE.clear()
 big=tmp_path/'big';big.mkdir();_synthetic_rows(big,8)
 assert len(w._tasks('p',big))==8 and w.fold_cache_state(big) is None and len(w._FOLD_CACHE)==0
 assert w.read('p',{'view':'summary'},big)['pagination']['total']==8
 # The byte cap also bounds several small ledgers together.
 monkeypatch.setattr(w,'FOLD_CACHE_MAX_LEDGER_BYTES',w._ledger(roots[0]).stat().st_size+w._ledger(roots[1]).stat().st_size+1)
 for root in roots:w._tasks('p',root)
 state=w.fold_cache_state(roots[2]);assert state['entries']<=2 and state['cached_ledger_bytes']<=w.FOLD_CACHE_MAX_LEDGER_BYTES


def test_digest_cache_is_capped_least_recently_used_and_stays_correct(tmp_path,monkeypatch):
 w._DIGEST_CACHE.clear();monkeypatch.setattr(w,'DIGEST_CACHE_MAX_ENTRIES',2)
 for index in range(3):
  (tmp_path/f'proof-{index}').write_text(f'result {index}');make(tmp_path,f'w{index}');move(tmp_path,f'w{index}','done',evidence=[f'proof-{index}'])
 summary=w.read('p',{'view':'summary'},tmp_path)
 assert all(r['current_acceptance']['status']=='CURRENT' for r in summary['tasks']) and len(w._DIGEST_CACHE)==2
 (tmp_path/'proof-0').write_text('result 0 changed')
 assert detail(tmp_path,'w0')['task']['currentness']['kind']=='EVIDENCE_CHANGED' and len(w._DIGEST_CACHE)<=2


def test_append_republishes_an_immutable_entry_while_readers_iterate(tmp_path):
 import threading
 w._FOLD_CACHE.clear();make(tmp_path,'seed');w._tasks('p',tmp_path)   # publish the one-row fold
 before=w._FOLD_CACHE[w._ledger(tmp_path)];rows_before=before['rows'];fold_before=before['by_project']
 make(tmp_path,'next')
 after=w._FOLD_CACHE[w._ledger(tmp_path)]
 assert after is not before and len(rows_before)==1 and len(after['rows'])==2   # the old entry was never mutated
 assert 'p' not in fold_before or set(fold_before['p'])=={'seed'}
 assert set(after['by_project']['p'])=={'seed','next'}
 # Concurrent readers during appends: no exception, every read internally consistent,
 # and the final published fold equals the ledger.
 errors=[];reads=[0];stop=threading.Event()
 def reader():
  try:
   while not stop.is_set():
    page=w.read('p',{'view':'summary','limit':100},tmp_path);reads[0]+=1
    assert page['pagination']['total']==len(page['tasks'])
    assert len({r['id'] for r in page['tasks']})==len(page['tasks'])
  except Exception as error:errors.append(error)
 threads=[threading.Thread(target=reader) for _ in range(4)]
 for t in threads:t.start()
 for index in range(40):make(tmp_path,f'con-{index}')
 stop.set()
 for t in threads:t.join()
 assert not errors and reads[0]>0
 lines=[line for line in w._ledger(tmp_path).read_text().splitlines() if line.strip()]
 assert w.fold_cache_state(tmp_path)['rows']==len(lines)==42 and len(w._tasks('p',tmp_path))==42


def test_absent_namespace_reads_retain_nothing_until_the_namespace_exists(tmp_path):
 w._FOLD_CACHE.clear();make(tmp_path,'real')
 w._tasks('p',tmp_path);before=w.fold_cache_state(tmp_path)
 for index in range(200):
  assert w._tasks(f'absent-{index}',tmp_path)=={}
  code,_,body=http.handle('/work/state',{'project':[f'absent-{index}'],'view':['summary']},'GET',repo_root=tmp_path)
  assert code==200 and json.loads(body)['tasks']==[]
 after=w.fold_cache_state(tmp_path)
 assert after['projects']==before['projects']==['p'] and after['stamp']==before['stamp']
 # The namespace that later gains a row is observable through the new stamp.
 w.task('absent-7',{'id':'first','title':'First','goal':'g'},tmp_path)
 assert set(w._tasks('absent-7',tmp_path))=={'first'} and 'absent-7' in w.fold_cache_state(tmp_path)['projects']


# ---- M5 D: measured raw-byte budgets on the c4-c6 shape (one gate, one parent, fifty children) ----
PARENT='WORK-c4c6-fixture-parent'
def _c4c6(root):
 make(root,'WORK-c4c6-fixture-gate');(root/'gate-result').write_text('observed gate result')
 move(root,'WORK-c4c6-fixture-gate','done',evidence=['gate-result'])
 make(root,PARENT,title='Fixture parent with fifty children')
 for i in range(1,51):
  make(root,'WORK-c4c6-fixture-child-%02d'%i,title='Fixture child %02d of the c4c6 set'%i,parent_work_id=PARENT,depends_on=['WORK-c4c6-fixture-gate'])


def _served(root,**query):
 code,_,raw=http.handle('/work/state',{'project':['p'],**{k:[str(v)] for k,v in query.items()}},'GET',repo_root=root)
 assert code==200,raw[:300];return raw,json.loads(raw)


def test_home_list_detail_and_graph_meet_the_accepted_raw_byte_budgets(tmp_path):
 _c4c6(tmp_path)
 home,summary=_served(tmp_path,view='summary',limit=12)
 assert len(home)<=30000,len(home)
 rows=summary['tasks'];assert len(rows)==12
 for row in rows:
  assert 'child_work_ids' not in row and isinstance(row['child_count'],int)
  assert len(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode())<=1300,row['id']
 assert next(row for row in rows if row['id']==PARENT)['child_count']==50
 # no ready row is delivered twice: page one names the ready set by id and opens one of them
 assert 'ready' not in summary and summary['ready_ids']==[r['id'] for r in w.read('p',{'view':'summary','limit':100},tmp_path)['tasks'] if r['status']=='ready'][:12]
 assert summary['next']==next(row for row in rows if row['status']=='ready')
 detail_raw,detail=_served(tmp_path,view='detail',id=PARENT)
 assert len(home)+len(detail_raw)<=50000,(len(home),len(detail_raw))
 assert detail['task']['child_count']==50 and 'child_work_ids' not in detail['task']
 children=detail['children'];assert (len(children['items']),children['total'],children['limit'],children['next_offset'])==(20,50,20,20)
 graph_raw,graph=_served(tmp_path,view='graph',parent_work_id=PARENT)
 assert len(graph_raw)<=30000,len(graph_raw)
 assert len(graph['nodes'])==50 and graph['pagination']['total']==51
 assert all(set(node)<={'id','title','task_kind','status','containment_issue','lifecycle','readiness','current_acceptance'} for node in graph['nodes'])
 assert {edge['kind'] for edge in graph['edges']}=={'contains','requires'}
 assert graph['node_read']['payload']=={'namespace':'p','view':'detail'} and graph['node_read']['id_field']=='id'
 assert graph['node_read']['http']['url']=='/work/state?project=p&view=detail' and graph['node_read']['http']['id_param']=='id'


def test_detail_relation_pages_continue_under_one_cut_without_gaps_or_repeats(tmp_path):
 _c4c6(tmp_path)
 _,first=_served(tmp_path,view='detail',id=PARENT);cut=first['read_cut']['revision'];seen=[r['id'] for r in first['children']['items']]
 page=first['children']
 while page['next_read']:
  payload=page['next_read']['payload'];assert payload['as_of']==cut and payload['id']==PARENT and payload['limit']==20
  value=w.read('p',payload,tmp_path);assert value['read_cut']['revision']==cut;page=value['children'];seen.extend(r['id'] for r in page['items'])
 assert seen==['WORK-c4c6-fixture-child-%02d'%i for i in range(1,51)]
 # an explicit owner page size is still honoured (bounded by the contract's 100)
 assert len(w.read('p',{'view':'detail','id':PARENT,'limit':50},tmp_path)['children']['items'])==50
 with pytest.raises(ValueError,match='owner contract'):w.read('p',{'view':'detail','id':PARENT,'limit':101},tmp_path)
 # a changed fold refuses the stale continuation instead of mixing pages
 make(tmp_path,'late',parent_work_id=PARENT)
 with pytest.raises(w.WorkConflict):w.read('p',first['children']['next_read']['payload'],tmp_path)


def test_every_work_stays_reachable_and_native_serves_the_same_bounded_projection(tmp_path):
 _c4c6(tmp_path)
 seen=[];payload={'view':'summary','limit':12}
 while payload:
  value=w.read('p',payload,tmp_path);seen.extend(r['id'] for r in value['tasks'])
  payload=value['pagination']['next_read']['payload'] if value['pagination']['next_read'] else None
 assert len(seen)==len(set(seen))==52
 for view in ({'view':'summary','limit':12},{'view':'detail','id':PARENT},{'view':'graph','parent_work_id':PARENT}):
  native=writing_tools.execute(tmp_path,'session-project','work','project',{'namespace':'p',**view})
  _,served=_served(tmp_path,**view)
  assert reads_owner.read_output_digest('project',served)==reads_owner.read_output_digest('project',native),view
 # a Work of another namespace is not read through this one
 with pytest.raises(ValueError,match='unavailable in this namespace'):w.read('other',{'view':'detail','id':PARENT},tmp_path)
