"""Optional Source execution accounting, public metadata fixtures, no inference."""
import copy,json
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_source_use_joins import source
from laplace.work import development_source as D,project_work as W
from laplace.writing import source_execution as X,records,delivery
from laplace.native import tools


def opted(s,*,native=3,apps=3,sessions=2,request='public-source-commission'):
 policy={'commission_request_id':request,'max_admitted_native_invocations':native,'max_app_admissions':apps,'max_sessions':sessions,'wall_seconds':1200}
 payload={**copy.deepcopy(s['payload']),'request_id':s['payload']['request_id']+'-allowance','expected_work_revision':W._task_revision(W._tasks('public',s['root'])['work']),'native_allowance':policy}
 grant=D.grant(s['root'],'public',payload,{'origin':'human'})['grant'];a=X.prepare_initial(s['root'],'public',s['parent']['id'],grant['id'])
 return grant,a,payload


def attached(s,*,native=3):
 grant,a,payload=opted(s,native=native);reservation=X.reserve_app(s['root'],a,'public-initial-turn',session_id=s['parent']['id'])
 records.bank(s['root'],{'record':'writing-turn','id':'WT-allowance','project':'public','session_id':s['parent']['id'],'mode':'work','text':'Public synthetic allowance identity; no model.','request_id':'public-initial-turn','source_execution':a,'source_admission_id':reservation['admission_id']})
 X.bind_app(s['root'],reservation,s['parent']['id'],'WT-allowance')
 return grant,a,payload


def read_wire(grant):return {'operation':'development_source','payload':{'action':'read','grant_id':grant['id'],'path':'src/answer.py','include_text':False}}


def test_actual_native_call_reentry_later_identical_arrival_and_late_metadata(source):
 s=source;grant,a,_=attached(s,native=2);wire=read_wire(grant)
 cut=D.cut(W._tasks('public',s['root'])['work'],s['root']);work=W._task_revision(W._tasks('public',s['root'])['work'])
 with delivery.incoming(transport_kind='direct-internal',request_id='same-rpc') as first:
  one=tools.call(s['root'],'public','work',wire,turn_id='WT-allowance',_incoming=first)
 assert one['source_allowance']['admitted']==1 and one['source_allowance']['remaining']==1 and one['source_allowance']['active']==1
 with delivery.incoming(transport_kind='direct-internal',request_id='same-rpc') as second:
  two=tools.call(s['root'],'public','work',wire,turn_id='WT-allowance',_incoming=second)
 assert first.native_invocation_id!=second.native_invocation_id and two['source_allowance']['admitted']==2 and two['source_allowance']['state']=='DRAINING'
 assert one['sha256']==two['sha256'] and one['read_receipt']['output_sha256']==two['read_receipt']['output_sha256']
 assert D.cut(W._tasks('public',s['root'])['work'],s['root'])==cut and W._task_revision(W._tasks('public',s['root'])['work'])==work
 with pytest.raises(X.AllowanceRefused) as error:tools.call(s['root'],'public','work',wire,turn_id='WT-allowance')
 denied=tools.tool_failure(s['root'],'public','work','development_source',wire['payload'],error.value,'WT-allowance')
 assert denied['source_allowance']['admitted']==2 and denied['source_allowance']['denied']==1
 (s['root']/'native-allowance-proof.json').write_text(json.dumps({'one':one,'two':two,'denied':denied},indent=2))


def test_invalid_gateway_arguments_spend_one_and_failure_keeps_carrier(source):
 s=source;grant,a,_=attached(s,native=2)
 with delivery.incoming(transport_kind='direct-internal') as holder:
  with pytest.raises(Exception) as error:tools.call(s['root'],'public','work',{'bad':'schema'},turn_id='WT-allowance',_incoming=holder)
  response=tools.tool_failure(s['root'],'public','work','',{},error.value,'WT-allowance')
 assert response['source_allowance']['admitted']==1 and response['source_allowance']['active']==0
 assert X.status(s['root'],a)['remaining']==1


def test_opted_source_cannot_be_used_from_unbound_turn_and_legacy_remains(source):
 s=source;grant,a,_=opted(s)
 with pytest.raises(X.AllowanceRefused):D.read(s['root'],'public',{'grant_id':grant['id'],'path':'src/answer.py'},s['door'])
 assert D.read(s['root'],'public',{'grant_id':s['grant']['id'],'path':'src/answer.py'},s['door'])['text']
 assert tools.execute(s['root'],'public','work','development_source',{'action':'read','grant_id':s['grant']['id'],'path':'src/answer.py'},turn_id='WT-parent')['text']
 assert X.status(s['root'],a)['state']=='READY'


def test_commission_policy_reissue_does_not_reset_and_changed_policy_refuses(source):
 s=source;grant,a,payload=attached(s,native=3);tools.call(s['root'],'public','work',read_wire(grant),turn_id='WT-allowance')
 later=copy.deepcopy(payload);later.update(request_id='reissued-source-grant',expected_work_revision=W._task_revision(W._tasks('public',s['root'])['work']))
 new=D.grant(s['root'],'public',later,{'origin':'human'})['grant'];resolved=X.prepare_initial(s['root'],'public',s['parent']['id'],new['id']);assert resolved['commission_id']==a['commission_id'] and X.status(s['root'],resolved)['admitted']==1
 later['request_id']='changed-policy-grant';later['expected_work_revision']=W._task_revision(W._tasks('public',s['root'])['work']);later['native_allowance']['max_admitted_native_invocations']=100
 with pytest.raises(ValueError,match='immutable'):D.grant(s['root'],'public',later,{'origin':'human'})


def test_parallel_last_slot_reservation_and_restart_use_metadata_only(source):
 s=source;grant,a,_=attached(s,native=1)
 def claim(_):
  with delivery.incoming() as h:
   try:X.claim_native(s['root'],'public','WT-allowance',h,{'operation':'public'});return h
   except X.AllowanceRefused:return None
 with ThreadPoolExecutor(max_workers=2) as pool:holders=list(pool.map(claim,range(2)))
 assert sum(h is not None for h in holders)==1;status=X.status(s['root'],a);assert status['admitted']==1 and status['active']==1 and status['denied']==1
 assert X.control(s['root'],'public','WT-allowance')['stop'] is False
 records.indexes.clear();assert X.status(s['root'],a)['admitted']==1
 X.settle_native(s['root'],next(h for h in holders if h),'SETTLED_SUCCESS');assert X.control(s['root'],'public','WT-allowance')['stop'] is True


def test_claim_lost_ack_reconciles_before_owner_and_unproven_claim_stops(source,monkeypatch):
 s=source;grant,a,_=attached(s);bank=records.bank
 def lost(root,row,**kw):
  result=bank(root,row,**kw)
  if row['record']=='writing-native-call-claim':raise OSError('public lost append acknowledgement')
  return result
 monkeypatch.setattr(records,'bank',lost)
 with delivery.incoming() as h:X.claim_native(s['root'],'public','WT-allowance',h,{});assert h.source_admitted
 assert X.status(s['root'],a)['admitted']==1
 monkeypatch.setattr(records,'bank',lambda root,row,**kw: (_ for _ in ()).throw(OSError('public before-append failure')) if row['record']=='writing-native-call-claim' else bank(root,row,**kw))
 with delivery.incoming() as h:
  with pytest.raises(X.AllowanceRefused):X.claim_native(s['root'],'public','WT-allowance',h,{'next':True})
 assert X.status(s['root'],a)['state']=='UNKNOWN' and X.status(s['root'],a)['remaining']==1


def test_app_session_reservation_recovery_and_turn_own_binding(source):
 s=source;grant,a,_=attached(s);reservation=X.reserve_app(s['root'],a,'public-review-event',new_session=True,role='review');assert reservation['may_create_session'] and reservation['session_id'] is None
 # Synthetic session metadata models the consumer's private creation marker.
 sid='WS-reserved-public';records.bank(s['root'],{'record':'writing-session','id':sid,'project':'public','provider':'codex','model':'gpt-6.1-sol','effort':'high','role':'review','source_execution':a,'source_admission_id':reservation['admission_id']})
 recovered=X.reserve_app(s['root'],a,'public-review-event',new_session=True,role='review');assert recovered['session_id']==sid and not recovered['may_create_session']
 X.bind_app(s['root'],recovered,sid,'WT-reserved');records.bank(s['root'],{'record':'writing-turn','id':'WT-reserved','session_id':sid,'project':'public','mode':'review','text':'synthetic','source_execution':a,'source_admission_id':reservation['admission_id']})
 assert X.for_turn(s['root'],'public','WT-reserved')['commission_id']==a['commission_id']
 continuation=X.reserve_app(s['root'],a,'CONT-public-review-event',session_id=s['parent']['id'],role='continuation');records.bank(s['root'],{'record':'writing-turn','id':'WT-cont','session_id':s['parent']['id'],'project':'public','mode':'work','text':'synthetic continuation','source_execution':a,'source_admission_id':continuation['admission_id']});X.bind_app(s['root'],continuation,s['parent']['id'],'WT-cont')
 assert X.for_turn(s['root'],'public','WT-cont')['commission_id']==a['commission_id'] and X.for_turn(s['root'],'public','WT-allowance')['commission_id']==a['commission_id']


def test_direct_request_execute_and_special_semantic_branch_share_incoming_unit(source,monkeypatch):
 from laplace.native import verbs
 s=source;grant,a,_=attached(s,native=3);payload=read_wire(grant)['payload'];classified=verbs.classify('development_source',payload,project='public',root=s['root']);assert classified.request
 result=tools.request(s['root'],'public','work',classified.request,turn_id='WT-allowance');assert result['source_allowance']['admitted']==1
 result=tools.execute(s['root'],'public','work','development_source',payload,turn_id='WT-allowance');assert result['source_allowance']['admitted']==2
 seen=[];monkeypatch.setattr(tools,'_technical_friction_call',lambda *a,**k:seen.append(True) or {'public':True})
 semantic=verbs.classify('corpus/friction-read',{},project='public',root=s['root']).request;assert semantic is not None
 out=tools.request(s['root'],'public','work',semantic,turn_id='WT-allowance');assert out['source_allowance']['admitted']==3 and len(seen)==1


def test_delivery_encoding_failure_retains_spent_claim_and_effect_reference(source):
 s=source;grant,a,_=attached(s,native=2)
 with delivery.incoming(transport_kind='direct-internal') as holder:
  response=tools.call(s['root'],'public','work',read_wire(grant),turn_id='WT-allowance',_incoming=holder)
  error=ValueError('public response encoding failed after owner result')
  failure=tools.tool_failure(s['root'],'public','work','development_source',read_wire(grant)['payload'],error,'WT-allowance')
 assert X.status(s['root'],a)['admitted']==1 and failure['source_allowance']['remaining']==1 and holder.source_settled=='DELIVERY_UNCERTAIN'


def test_empty_slot_drains_and_wall_expiry_does_not_claim_python_effect_stopped(source,monkeypatch):
 s=source;grant,a,_=attached(s,native=1)
 with delivery.incoming() as holder:X.claim_native(s['root'],'public','WT-allowance',holder,{})
 waiting=X.control(s['root'],'public','WT-allowance');assert waiting['state']=='DRAINING' and waiting['active_for_turn']==1 and not waiting['stop']
 deadline=X.dt.datetime.fromisoformat(waiting['deadline_at']);monkeypatch.setattr(X,'_now',lambda:deadline+X.dt.timedelta(seconds=1))
 expired=X.control(s['root'],'public','WT-allowance');assert expired['stop'] and expired['reason']=='COMMISSION_WALL_EXPIRED' and expired['active_for_turn']==1
 with pytest.raises(X.AllowanceRefused):X.reserve_app(s['root'],a,'CONT-no-room',session_id=s['parent']['id'],role='continuation')
 assert X.status(s['root'],a)['active']==1


def test_unresolved_new_session_creation_never_becomes_false_absence(source):
 s=source;grant,a,_=attached(s);first=X.reserve_app(s['root'],a,'new-session-unknown',new_session=True,role='review');assert first['may_create_session']
 with pytest.raises(X.AllowanceRefused,match='SESSION_CREATION_UNKNOWN'):X.reserve_app(s['root'],a,'new-session-unknown',new_session=True,role='review')
 records.indexes.clear();assert X.status(s['root'],a)['state']=='UNKNOWN'
 with pytest.raises(X.AllowanceRefused):X.reserve_app(s['root'],a,'CONT-unknown',session_id=s['parent']['id'],role='continuation')


def test_unsupported_policy_fields_and_foreign_initial_selector_refuse(source):
 s=source;grant,a,payload=opted(s)
 for policy in [{**a['policy'],'max_tokens':10},{**a['policy'],'max_admitted_native_invocations':True},{**a['policy'],'max_sessions':4},{**a['policy'],'wall_seconds':D.MAX_LIFETIME_S+1}]:
  bad={**payload,'request_id':'invalid-policy-request','expected_work_revision':W._task_revision(W._tasks('public',s['root'])['work']),'native_allowance':policy}
  with pytest.raises(ValueError):D.grant(s['root'],'public',bad,{'origin':'human'})
 with pytest.raises(ValueError):X.prepare_initial(s['root'],'public',s['review']['id'],grant['id'])


def test_accounting_cold_warm_append_reads_no_transcript_bodies(source):
 s=source;grant,a,_=attached(s)
 for n in range(20):records.bank(s['root'],{'record':'writing-turn','id':'WT-public-long-'+str(n),'project':'public','session_id':s['parent']['id'],'mode':'work','text':'Public unrelated body. '*1500})
 records.indexes.clear();X.status(s['root'],a);idx=records.index(s['root']);cold=copy.deepcopy(idx.stats)
 X.status(s['root'],a);warm=copy.deepcopy(idx.stats)
 with delivery.incoming() as holder:X.claim_native(s['root'],'public','WT-allowance',holder,{'accounting':'probe'})
 X.status(s['root'],a);appended=copy.deepcopy(idx.stats)
 assert cold.get('custody_bodies_opened')==warm.get('custody_bodies_opened')==appended.get('custody_bodies_opened')==0 and cold.get('retained_content_body_bytes')==0
 (s['root']/'metadata-cost-proof.json').write_text(json.dumps({'cold':cold,'warm':warm,'necessary_claim_append':appended,'scope':'Public20long unrelated messages; existing metadata index cold raw-journal scan/warm/suffix refresh. No body custody hydration or general performance claim.'},indent=2))


def test_private_holder_intent_and_completed_dispatch_cannot_be_reused_as_new_work(source):
 s=source;grant,a,_=attached(s)
 with delivery.incoming() as holder:
  X.claim_native(s['root'],'public','WT-allowance',holder,{'original':True})
  assert X.claim_native(s['root'],'public','WT-allowance',holder,{'original':True})==holder.source_claim
  with pytest.raises(X.AllowanceRefused,match='intent changed'):X.claim_native(s['root'],'public','WT-allowance',holder,{'different':True})
  X.settle_native(s['root'],holder,'SETTLED_SUCCESS')
  with pytest.raises(X.AllowanceRefused,match='already settled'):X.claim_native(s['root'],'public','WT-allowance',holder,{'original':True})
 assert X.status(s['root'],a)['admitted']==1 and X.status(s['root'],a)['active']==0


def test_source_effect_and_tool_audit_keep_same_claim_and_human_recovery_read(source):
 s=source;grant,a,_=attached(s,native=3)
 wire={'operation':'development_source','payload':{'action':'candidate','grant_id':grant['id'],'files':[{'path':'src/answer.py','before_sha256':D._pin(s['checkout']/'src/answer.py'),'edits':[{'old':'unique old','new':'new chosen'}]}]}}
 result=tools.call(s['root'],'public','work',wire,turn_id='WT-allowance')
 row=D._latest(W._tasks('public',s['root'])['work'],'candidate',result['candidate_id']);link=row['actor']['source_execution'];assert link['commission_id']==a['commission_id']
 idx=records.index(s['root']);audit=[r for r in idx.by_turn['WT-allowance'] if r['record']=='writing-tool-action'];assert len(audit)==1 and audit[0]['claim_id']==link['claim_id'] and audit[0]['native_invocation_id']==link['native_invocation_id']
 from laplace.web import project_work_surface
 handle=result['source_allowance']['read']['http'];code,_,body=project_work_surface.handle(handle['url'],{},handle['method'],json.dumps(handle['payload']).encode(),s['root']);assert code==200
 assert json.loads(body)['execution_allowances'][0]['admitted']==1
 assert delivery.emitted(result)<16000


def test_metadata_uncertainty_control_and_parent_session_gate_are_fail_closed(source,monkeypatch):
 s=source;grant,a,_=attached(s)
 with pytest.raises(X.AllowanceRefused,match='original session'):X.reserve_app(s['root'],a,'wrong-parent-session',session_id=s['other']['id'] if 'other' in s else s['review']['id'],role='continuation')
 real=records.index;monkeypatch.setattr(records,'index',lambda *_a,**_k: (_ for _ in ()).throw(OSError('public unavailable metadata')))
 control=X.control(s['root'],'public','WT-allowance');assert control['stop'] and control['state']=='UNKNOWN'
 monkeypatch.setattr(records,'index',real)
 records.bank(s['root'],{'record':'writing-reply','id':'WR-terminal-public','project':'public','turn_id':'WT-allowance','status':'completed','text':'public completed fixture'})
 with pytest.raises(X.AllowanceRefused,match='TURN_NOT_ACTIVE'):tools.call(s['root'],'public','work',read_wire(grant),turn_id='WT-allowance')
 assert X.status(s['root'],a)['admitted']==0


def test_total_claim_and_stop_write_failure_prevents_owner_and_marks_existing_job(source,monkeypatch):
 from laplace.writing import turn_jobs
 s=source;grant,a,_=attached(s);bank=records.bank
 job={'source_execution':a};monkeypatch.setitem(turn_jobs._JOBS,'WT-allowance',job)
 def unavailable(root,row,**kw):
  if row['record'] in {'writing-native-call-claim','writing-source-execution-stop'}:raise OSError('public total journal unavailable')
  return bank(root,row,**kw)
 monkeypatch.setattr(records,'bank',unavailable)
 entered=[];monkeypatch.setattr(tools,'_call_public_impl',lambda *a,**k:entered.append(True) or {})
 with pytest.raises(X.AllowanceRefused):tools.call(s['root'],'public','work',read_wire(grant),turn_id='WT-allowance')
 assert not entered and job['source_execution_unknown']=='CLAIM_PUBLICATION_UNKNOWN' and X.control(s['root'],'public','WT-allowance')['stop']
 monkeypatch.setattr(records,'bank',bank);records.indexes.clear();assert X.status(s['root'],a)['admitted']==0
 # No invented persisted spent/stop row after both writes failed; this actual job remains uncertain/stopped.
 assert X.control(s['root'],'public','WT-allowance')['state']=='UNKNOWN'


def test_source_bound_generic_spawn_refuses_before_owner_legacy_unchanged(source,monkeypatch):
 s=source;grant,a,_=attached(s);entered=[]
 monkeypatch.setattr(tools._operations,'_execute',lambda *a,**k:entered.append(True) or {'public':True})
 with pytest.raises(X.AllowanceRefused,match='unsupported generic'):tools.execute(s['root'],'public','work','dispatch_launch',{'id':'public-dispatch'},turn_id='WT-allowance')
 assert not entered and X.status(s['root'],a)['admitted']==1
 # Same trusted identity test without Source attachment retains the existing legacy route.
 tools.execute(s['root'],'public','work','dispatch_launch',{'id':'public-dispatch'},turn_id='WT-parent')
 assert len(entered)==1


def test_spawn_guard_checks_incoming_even_when_explicit_parent_is_legacy(source):
 s=source;grant,a,_=attached(s,native=4)
 assert X.guard_spawn(s['root'],'public',parent_turn_id='WT-parent') is None
 reserved=X.reserve_app(s['root'],a,'canonical-review-spawn',new_session=True,role='review')
 assert X.guard_spawn(s['root'],'public',parent_turn_id='WT-allowance',reservation=reserved)==a
 with delivery.incoming() as holder,delivery.invocation(incoming=holder):
  X.claim_native(s['root'],'public','WT-allowance',holder,{'spawn':'probe'})
  with pytest.raises(X.AllowanceRefused,match='unsupported generic'):
   X.guard_spawn(s['root'],'public',parent_turn_id='WT-parent')
  assert X.guard_spawn(s['root'],'public',parent_turn_id='WT-parent',reservation=reserved)==a
  with pytest.raises(X.AllowanceRefused,match='crossed project'):
   X.guard_spawn(s['root'],'another',parent_turn_id=None)
  with pytest.raises(X.AllowanceRefused,match='reservation unavailable'):
   X.guard_spawn(s['root'],'public',reservation={**reserved,'admission_id':'SA-absent'})
 X.stop(s['root'],a,'EXPLICIT_STOP')
 with pytest.raises(X.AllowanceRefused,match='cannot admit'):
  X.guard_spawn(s['root'],'public',reservation=reserved)


def test_existing_session_generations_do_not_duplicate_accounting_identities(source):
 s=source;grant,a,_=opted(source)
 reservation=X.reserve_app(s['root'],a,'real-existing-session',session_id=s['parent']['id'])
 original=records.exact_record('public',reservation['admission_id'],s['root'])[0]
 for n in range(2):
  records.bank(s['root'],{**s['parent'],'source_execution':a,'source_admission_id':reservation['admission_id'],'name':'Public update '+str(n)})
  X.bind_app(s['root'],reservation,s['parent']['id'])
 replay=X.reserve_app(s['root'],a,'real-existing-session',session_id=s['parent']['id'])
 assert replay['session_id']==s['parent']['id'] and X.status(s['root'],a)['app_admissions']==1 and X.status(s['root'],a)['sessions']==1
 records.indexes.clear();assert X.status(s['root'],a)['state']=='ACTIVE'
 # Only legitimate WS generations use the latest projection: duplicate immutable
 # reservation identity remains ambiguous, never a tolerant last-wins account.
 records.bank(s['root'],original)
 assert X.status(s['root'],a)['state']=='UNKNOWN'


def test_direct_call_settles_but_outer_delivery_retains_same_active_claim(source):
 s=source;grant,a,_=attached(s,native=2)
 direct=tools.call(s['root'],'public','work',read_wire(grant),turn_id='WT-allowance')
 assert direct['source_allowance']['active']==0
 with delivery.incoming(transport_kind='codex-appserver') as holder:
  outer=tools.call(s['root'],'public','work',read_wire(grant),turn_id='WT-allowance',_incoming=holder)
  assert outer['source_allowance']['active']==1 and holder.source_settled is None
  assert not X.control(s['root'],'public','WT-allowance')['stop']
 assert holder.source_settled=='SETTLED_SUCCESS' and X.control(s['root'],'public','WT-allowance')['stop']
 assert X.status(s['root'],a)['admitted']==2


def test_idempotent_bind_returns_actual_coordinates_from_original_unbound_reservation(source):
 s=source;grant,a,_=attached(s)
 original=X.reserve_app(s['root'],a,'first-wd-double-bind',new_session=True,role='review')
 assert original['session_id'] is None
 records.bank(s['root'],{**s['review'],'source_execution':a,'source_admission_id':original['admission_id']})
 first=X.bind_app(s['root'],original,s['review']['id'])
 before=records.index(s['root']).stats.copy()
 again=X.bind_app(s['root'],original,s['review']['id'])
 assert again==first and again['session_id']==s['review']['id'] and again['turn_id'] is None
 assert records.index(s['root']).stats==before and X.status(s['root'],a)['app_admissions']==2


def test_shared_drain_waits_for_peer_delivery_while_turn_count_is_observational(source):
 s=source;grant,a,_=attached(s,native=1)
 reservation=X.reserve_app(s['root'],a,'shared-peer-review',session_id=s['review']['id'],role='review')
 records.bank(s['root'],{'record':'writing-turn','id':'WT-peer-source','project':'public','session_id':s['review']['id'],'mode':'review','text':'Public peer','source_execution':a,'source_admission_id':reservation['admission_id']})
 X.bind_app(s['root'],reservation,s['review']['id'],'WT-peer-source')
 with delivery.incoming() as holder:
  X.claim_native(s['root'],'public','WT-peer-source',holder,{'public':'peer final response'})
  parent=X.control(s['root'],'public','WT-allowance');peer=X.control(s['root'],'public','WT-peer-source')
  assert parent['active']==peer['active']==1 and parent['active_for_turn']==0 and peer['active_for_turn']==1
  assert not parent['stop'] and not peer['stop']
  X.settle_native(s['root'],holder,'SETTLED_SUCCESS')
 assert X.control(s['root'],'public','WT-allowance')['stop'] and X.control(s['root'],'public','WT-peer-source')['stop']
 with pytest.raises(X.AllowanceRefused):X.reserve_app(s['root'],a,'no-new-parent',session_id=s['parent']['id'],role='continuation')


# ------------------------------------------------------------- the detached Source reviewer, actual separate processes
#: Both the transient adapter and the detached host boot this before any application import: the runtime guard (only the
#: interpreter may launch; no network, no canonical state), the deterministic catalogue and a gated stub at the runtime
#: lookup. The reviewer stub spawns one real provider stand-in through the turn's own on_spawn registrar and waits for
#: the test's gate (then records ACCEPT through the real native door) or for that process to be stopped.
DETACHED_RUNTIME = r'''
import os, sys
sys.path.insert(0, os.environ['LAPLACE_GUARD_TESTS'])
import runtime_guard
runtime_guard.install(); runtime_guard.ARMED = True
import json, subprocess, time
from pathlib import Path
from laplace.writing import provider as wp
CATALOGUE = {'providers': [{'id': 'codex', 'available': True, 'models': [{'id': 'gpt-6.1-sol', 'efforts': ['high'], 'supports_effort': True}]}]}
wp.capabilities = lambda *a, **k: json.loads(json.dumps(CATALOGUE))
wp.provider_catalogue = lambda *a, **k: json.loads(json.dumps(CATALOGUE))
wp.context_window_advertised = lambda *a, **k: None
class Stub:
    def __init__(self, root, provider, model, effort, native_id, emit, mode, **kw):
        self.root, self.mode, self.turn_id, self.project = Path(root), mode, kw['logical_turn_id'], kw['project']
        self.native_id, self.inference_started, self.process = native_id, False, None
    def _note(self, **facts):
        runs = self.root / 'stub-runs'; runs.mkdir(exist_ok=True)
        (runs / (self.turn_id + '.json')).write_text(json.dumps({'host_pid': os.getpid(), 'mode': self.mode, **facts}))
    def run(self, prompt):
        if self.mode != 'review':
            self._note(state='completed'); return {'status': 'completed', 'text': 'continuation fixture'}
        self.process = subprocess.Popen([sys.executable, '-S', '-c', 'import time; time.sleep(60)'], start_new_session=True)
        self.on_spawn(self.process, 'provider'); self.inference_started = True
        self._note(state='held', provider_pid=self.process.pid)
        gate = self.root / 'review-gate.json'
        while not gate.exists() and self.process.poll() is None:time.sleep(0.05)
        if self.process.poll() is not None:
            self._note(state='stopped'); return {'status': 'interrupted', 'text': '', 'error': 'provider process stopped'}
        from laplace.native import tools; from laplace.work import project_work as W
        tools.execute(self.root, self.project, 'review', 'work_review', {**json.loads(gate.read_text()), 'id': 'work', 'phase': 'review',
            'expected_work_revision': W._task_revision(W._tasks(self.project, self.root)['work'])}, turn_id=self.turn_id)
        self.process.terminate(); self.process.wait(timeout=5)
        self._note(state='completed'); return {'status': 'completed', 'text': 'reviewed'}
    def interrupt(self):
        if self.process is not None and self.process.poll() is None:self.process.terminate()
        return {}
wp.WritingTurn = Stub
'''


def _wait_for(predicate, timeout=40.0, what='condition'):
 import time
 deadline=time.perf_counter()+timeout
 while time.perf_counter()<deadline:
  value=predicate()
  if value:return value
  time.sleep(0.05)
 raise AssertionError('timed out waiting for '+what)


def _detached_setup(s):
 """The Source-bound parent (WT-allowance), its exact applied candidate and qualified handoff; nothing transported yet."""
 from laplace.work import project_work_review as R
 voice=s['root']/'profiles/voice/gerard-technical-v1.md';voice.parent.mkdir(parents=True,exist_ok=True);voice.write_text('# Public voice\nVersion: public-v1\nBe concrete.\n')
 grant,a,_=attached(s,native=4);door={'origin':'native','turn_id':'WT-allowance'}
 c=D.candidate(s['root'],'public',{'grant_id':grant['id'],'files':[{'path':'src/answer.py','before_sha256':D._pin(s['checkout']/'src/answer.py'),
   'edits':[{'old':'unique old','new':'detached reviewer'}]}]},door)
 D.apply(s['root'],'public',{'candidate_id':c['candidate_id']},door)
 pins={p:D._pin(s['checkout']/p) for p in ['src/answer.py','evaluator.py']}
 h=R.record('public',{'id':'work','phase':'handoff','request_id':'public-detached-handoff','expected_work_revision':W._task_revision(W._tasks('public',s['root'])['work']),
   'obligations':['source'],'source_basis':{'grant_id':grant['id'],'candidate_id':c['candidate_id']},'pins':pins},s['root'],door=door)
 return grant,a,h['phase']['id']


def _transient_adapter(s,tmp_path,turn_id='WT-allowance'):
 """The ACTUAL Claude stdio MCP adapter of a turn (the parent by default), as its own process."""
 import os,subprocess,sys
 from pathlib import Path
 runtime=tmp_path/'detached-runtime';runtime.mkdir(exist_ok=True);(runtime/'sitecustomize.py').write_text(DETACHED_RUNTIME)
 tests=Path(__file__).resolve().parent;source=Path(tools.__file__).resolve().parents[2]
 env={**os.environ,'PYTHONPATH':os.pathsep.join(map(str,[runtime,source,tests])),'LAPLACE_TEST_PROCESS':'1',
      'LAPLACE_GUARD_TESTS':str(tests),'LAPLACE_GUARD_LOG':str(tmp_path/'guard-denials.jsonl')}
 process=subprocess.Popen([sys.executable,'-m','laplace.native.tools','--root',str(s['root']),'--project','public','--mode','work',
   '--turn-id',turn_id],cwd=str(s['root']),env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
 process.stdin.write(json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})+'\n');process.stdin.flush()
 assert json.loads(process.stdout.readline())['id']==1
 return process


def _event_rows(s,event_id):
 from laplace.work import work_delivery as WD
 return [r for r in W._tasks('public',s['root'])['work'].get('deliveries') or () if r.get('kind')==WD.EVENT and r.get('id')==event_id]


@pytest.mark.parametrize('outcome',['released','stopped'])
def test_detached_reviewer_survives_adapter_exit_and_returns_once_on_the_same_account(source,tmp_path,outcome):
 """The orphan route: the reviewer used to be a daemon thread of the parent's MCP adapter and was ORPHANED when that
 adapter exited with the parent CLI. The real adapter now hands the exact Source review to a one-shot host of its own;
 the host replays the original reservation (no new admission, session or quota), keeps ownership through terminal
 settlement and the once-only parent return, and honours the exact Stop."""
 from laplace.writing import child_hosts,turn_control
 s=source;grant,a,handoff=_detached_setup(s)
 adapter=_transient_adapter(s,tmp_path);host=None
 try:
  adapter.stdin.write(json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'laplace_project','arguments':{'operation':'work_delivery','payload':{
    'action':'submit','work_id':'work','expected_work_revision':W._task_revision(W._tasks('public',s['root'])['work']),'handoff_id':handoff,'obligation_id':'source',
    'recipient_binding_id':s['binding']['id'],'parent_return':{'admit_idle':True,'max_attempts':1,'max_depth':1}}}}})+'\n');adapter.stdin.flush()
  answer=json.loads(adapter.stdout.readline());event=json.loads(answer['result']['content'][0]['text'])['event']
  assert event['state']=='ADMITTED',event
  review_turn,review_session=event['admitted']['turn_id'],event['admitted']['session_id']
  # the parent's CLI ends: its adapter exits and its turn is terminal
  adapter.stdin.close();assert adapter.wait(timeout=15)==0
  records.bank(s['root'],{'record':'writing-reply','id':'WR-detached-parent','turn_id':'WT-allowance','session_id':s['parent']['id'],'project':'public','status':'completed','text':'Parent ended after submit'})
  held=_wait_for(lambda:(s['root']/'stub-runs'/(review_turn+'.json')).is_file() and json.loads((s['root']/'stub-runs'/(review_turn+'.json')).read_text()),what='held reviewer')
  execution=child_hosts.child_execution(s['root'],review_session);host=execution['host']
  assert execution['state']=='RUNNING' and child_hosts._process_matches(host) and host['pid']==held['host_pid'] not in (adapter.pid,__import__('os').getpid())
  assert [p['pid'] for p in execution['active_provider_processes']]==[held['provider_pid']]
  reserved=[r for r in _event_rows(s,event['id']) if r['state']=='RESERVED'][-1]
  assert records.fold_records(s['root'])['turns'][review_turn]['source_admission_id']==reserved['source_admission_id']
  standing=X.status(s['root'],a);assert (standing['app_admissions'],standing['sessions'])==(2,2),standing
  if outcome=='released':
   (s['root']/'review-gate.json').write_text(json.dumps({'request_id':'public-detached-verdict','handoff_id':handoff,'obligation_id':'source','verdict':'ACCEPT'}))
  else:
   stopped=turn_control.interrupt_turn(s['root'],{'turn_id':review_turn,'project':'public'});assert stopped['turn_ids']==[review_turn]
  _wait_for(lambda:not child_hosts._process_matches(host),what='the reviewer host to finish its owned work and exit')
  states=[r['state'] for r in _event_rows(s,event['id'])]
  turns=records.fold_records(s['root'])['turns'];replies=[t for t in turns.values() if t.get('request_id')==event['id']]
  assert len(replies)==1 and replies[0]['reply']['status']==('completed' if outcome=='released' else 'interrupted')
  assert states.count('RESULT')==1 and states.count('CONTINUED')==1 and states[-1]=='CONTINUED',states
  [continuation]=[t for t in turns.values() if t.get('request_id')=='CONT-'+event['id']]
  assert continuation['session_id']==s['parent']['id'] and continuation['reply']['status']=='completed'
  ran=json.loads((s['root']/'stub-runs'/(continuation['id']+'.json')).read_text())
  assert ran['host_pid']==host['pid'], 'the parent return was admitted by the same detached owner before it exited'
  assert not child_hosts._process_matches({'pid':held['provider_pid'],'created_at':execution['active_provider_processes'][0]['created_at']})
  standing=X.status(s['root'],a);assert (standing['app_admissions'],standing['sessions'])==(3,2),standing
  if outcome=='released':
   from laplace.work import work_delivery as WD
   assert WD.status(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']['acceptance']['satisfied']
  # recovery afterwards replays nothing: no second reviewer, return or account admission
  from laplace.work import work_delivery as WD
  WD.recover(s['root'],'public',{'event_id':event['id']},{'origin':'human'})
  assert [r['state'] for r in _event_rows(s,event['id'])].count('CONTINUED')==1 and X.status(s['root'],a)['app_admissions']==3
 finally:
  if adapter.poll() is None:adapter.kill();adapter.wait(timeout=5)
  if host and child_hosts._process_matches(host):child_hosts._terminate_owned_process(host)


def test_detached_host_entry_replays_only_the_original_reservation_and_refuses_other_requests(source,monkeypatch):
 """The host's one entry rebuilds the reservation from the canonical owners: same admission, no new quota; a lost
 admission acknowledgement reconciles the same turn; any other request, and an unreserved event, refuse."""
 from laplace.writing import turn_admission as A,turn_execution,provider
 from laplace.work import work_delivery as WD
 s=source;grant,a,handoff=_detached_setup(s);launches=[]
 monkeypatch.setattr(provider,'capabilities',lambda *x,**k:{'providers':[{'id':'codex','available':True,'models':[{'id':'gpt-6.1-sol','efforts':['high'],'supports_effort':True}]}]})
 monkeypatch.setattr(provider,'context_window_advertised',lambda *x,**k:None)
 monkeypatch.setattr(turn_execution,'start',lambda launch:launches.append(launch))
 real=A.start_source_turn;seen=[]
 def transport(root,request,reservation,*,delivery_event=None,source_event=None):
  if not source_event:return real(root,request,reservation,delivery_event=delivery_event)
  seen.append({'request':dict(request),'admission_id':reservation['admission_id']})
  for wrong in [{'request_id':'WD-other'},{'session_id':s['parent']['id']},{'mode':'work'},{'project':'another'}]:
   with pytest.raises(ValueError,match='original Work reservation'):WD.start_source_review(root,'public',source_event,{**request,**wrong})
  before=X.status(root,a)
  monkeypatch.setattr(A,'start_source_turn',real)
  try:admitted=WD.start_source_review(root,'public',source_event,request)   # what the detached host runs
  finally:monkeypatch.setattr(A,'start_source_turn',transport)
  after=X.status(root,a);assert (after['app_admissions'],after['sessions'])==(before['app_admissions'],before['sessions'])
  raise OSError('fixture: the host admitted the turn but its acknowledgement was lost')
 monkeypatch.setattr(A,'start_source_turn',transport)
 event=WD.submit(s['root'],'public',{'action':'submit','work_id':'work','expected_work_revision':W._task_revision(W._tasks('public',s['root'])['work']),
   'handoff_id':handoff,'obligation_id':'source','recipient_binding_id':s['binding']['id']},{'origin':'native','turn_id':'WT-allowance'})['event']
 assert event['state']=='SUBMITTED' and 'acknowledgement was lost' in event['last_error'] and len(launches)==1
 review=launches[0];assert records.fold_records(s['root'])['turns'][review.turn_id]['source_admission_id']==seen[0]['admission_id']
 counted=X.status(s['root'],a)
 recovered=WD.recover(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']
 assert recovered['state']=='ADMITTED' and recovered['admitted']['turn_id']==review.turn_id and recovered['admitted']['recovered'] is True
 assert len(launches)==1 and len(seen)==1 and X.status(s['root'],a)['app_admissions']==counted['app_admissions']
 # the event is no longer RESERVED: the host entry refuses to admit it again
 with pytest.raises(ValueError,match='original Work reservation'):WD.start_source_review(s['root'],'public',event['id'],seen[0]['request'])
 turn_execution._finish(review,{'status':'interrupted'})


def _codex_runtime(monkeypatch,launches):
 from laplace.writing import provider,turn_execution
 monkeypatch.setattr(provider,'capabilities',lambda *x,**k:{'providers':[{'id':'codex','available':True,'models':[{'id':'gpt-6.1-sol','efforts':['high'],'supports_effort':True}]}]})
 monkeypatch.setattr(provider,'context_window_advertised',lambda *x,**k:None)
 monkeypatch.setattr(turn_execution,'start',lambda launch:launches.append(launch))


def test_reply_before_admitted_publication_is_settled_once_without_recovery(source,monkeypatch):
 """The independently reproduced HOLD (runtime-settle-race-001), same ordering: inside the transport the recipient's
 turn is admitted, banks its terminal reply and runs the terminal hook while the event is still RESERVED (the hook
 settles nothing); only then does the submitter publish DELIVERED/ADMITTED. The saved reply must still settle, once,
 with no manual Recover, and the event must never move back from RESULT/CONTINUED."""
 from laplace.work import work_delivery as WD
 from laplace.writing import turn_admission as A
 s=source;grant,account,handoff=_detached_setup(s);observed={};launches=[];hooks=[]
 _codex_runtime(monkeypatch,launches)
 real=A.start_source_turn;settle=WD.settle_turn
 monkeypatch.setattr(WD,'settle_turn',lambda *a,**k:hooks.append(a[3]) or settle(*a,**k))
 def immediate(root,payload,reservation,*,source_event=None,**kw):
  if not source_event:return real(root,payload,reservation,**kw)   # the parent return: the real admission owner
  sid=payload['session_id'];tid='WT-immediate-actual-hook'
  WD.source_admission(root,'public',source_event,sid,reservation)
  records.bank(root,{'record':'writing-turn','id':tid,'project':'public','session_id':sid,'mode':'review','text':'Controlled immediate reply seam; no inference.','request_id':payload['request_id'],'source_execution':reservation['attachment'],'source_admission_id':reservation['admission_id']})
  X.bind_app(root,reservation,sid,tid)
  records.bank(root,{'record':'writing-reply','id':'WR-immediate-actual-hook','turn_id':tid,'project':'public','session_id':sid,'status':'completed','text':'Controlled terminal; no scientific acceptance.'})
  observed['state_at_terminal']=WD._history(WD._task_of_event(root,'public',source_event),source_event)[-1]['state']
  observed['settled']=WD.settle_turn(root,'public',sid,tid,{'status':'completed','text':'Controlled terminal.'})
  return {'session_id':sid,'turn_id':tid}
 monkeypatch.setattr(A,'start_source_turn',immediate)
 event=WD.submit(s['root'],'public',{'action':'submit','work_id':'work','expected_work_revision':W._task_revision(W._tasks('public',s['root'])['work']),'handoff_id':handoff,'obligation_id':'source','recipient_binding_id':s['binding']['id'],'parent_return':{'admit_idle':True,'max_attempts':1,'max_depth':1}},{'origin':'native','turn_id':'WT-allowance'})['event']
 assert observed=={'state_at_terminal':'RESERVED','settled':[]}, 'the reproduced ordering: the hook ran before ADMITTED and settled nothing'
 states=[r['state'] for r in _event_rows(s,event['id'])]
 assert states==['SUBMITTED','RESERVED','DELIVERED','ADMITTED','RESULT','CONTINUED'] and event['state']=='CONTINUED',states
 [result]=[r for r in _event_rows(s,event['id']) if r['state']=='RESULT']
 assert result['turn_id']=='WT-immediate-actual-hook' and result['result']['status']=='completed' and result['recipient_ack']=='TERMINAL'
 assert len(launches)==1 and launches[0].session_id==s['parent']['id'], 'exactly one once-only parent continuation'
 # a late or repeated terminal hook and a later Recover change nothing
 assert WD.settle_turn(s['root'],'public',result['session_id'],'WT-immediate-actual-hook',{'status':'completed'})==[]
 WD.recover(s['root'],'public',{'event_id':event['id']},{'origin':'human'})
 assert [r['state'] for r in _event_rows(s,event['id'])]==states and len(launches)==1
 assert X.status(s['root'],account)['app_admissions']==3
 from laplace.writing import turn_execution
 turn_execution._finish(launches[0],{'status':'interrupted'})


def test_pending_parent_recover_from_a_transient_adapter_returns_through_a_detached_host(source,tmp_path,monkeypatch):
 """The acknowledged lifetime gap, actual processes: the reviewer settles while the original parent is busy
 (PENDING_PARENT); the parent ends; an unrelated author turn's ACTUAL Claude MCP adapter recovers the event and exits.
 The once-only continuation must run in a one-shot host of its own, replaying the reservation the return banked, in the
 original parent session, on the same account; the adapter's exit must not take it down."""
 from laplace.writing import child_hosts,turn_execution as T
 from laplace.work import work_delivery as WD
 s=source;grant,account,handoff=_detached_setup(s);launches=[]
 _codex_runtime(monkeypatch,launches)
 parent=s['parent']['id']
 child_hosts._begin_child_execution(s['root'],parent,{'state':'RUNNING','turn_id':'WT-allowance','session_id':parent,'project':'public','host':child_hosts._process_identity()})
 event=WD.submit(s['root'],'public',{'action':'submit','work_id':'work','expected_work_revision':W._task_revision(W._tasks('public',s['root'])['work']),'handoff_id':handoff,'obligation_id':'source','recipient_binding_id':s['binding']['id'],'parent_return':{'admit_idle':True,'max_attempts':1,'max_depth':1}},{'origin':'native','turn_id':'WT-allowance'})['event']
 [review]=launches;result={'status':'completed','text':'Controlled reviewer terminal; no verdict.'}
 T._bank_reply(review,result);T._finish(review,result)
 pending=_event_rows(s,event['id'])[-1];assert pending['state']=='PENDING_PARENT' and 'session is working' in pending['reason'],pending
 assert X.status(s['root'],account)['app_admissions']==3, 'the return banked its continuation reservation before deferring'
 records.bank(s['root'],{'record':'writing-reply','id':'WR-parent-ended','turn_id':'WT-allowance','session_id':parent,'project':'public','status':'completed','text':'Parent ended'})
 child_hosts._finish_child_execution(s['root'],parent,'WT-allowance','completed')
 adapter=_transient_adapter(s,tmp_path,'WT-other');host=None
 try:
  adapter.stdin.write(json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'laplace_project','arguments':{'operation':'work_delivery',
    'payload':{'action':'recover','event_id':event['id']}}}})+'\n');adapter.stdin.flush()
  recovered=json.loads(json.loads(adapter.stdout.readline())['result']['content'][0]['text'])['event']
  assert recovered['state']=='CONTINUED',recovered
  adapter.stdin.close();assert adapter.wait(timeout=15)==0
  turns=lambda:[t for t in records.fold_records(s['root'])['turns'].values() if t.get('request_id')=='CONT-'+event['id']]
  [continuation]=_wait_for(turns,what='the continuation turn')
  ran=_wait_for(lambda:(s['root']/'stub-runs'/(continuation['id']+'.json')).is_file() and json.loads((s['root']/'stub-runs'/(continuation['id']+'.json')).read_text()),what='continuation run')
  host={'pid':ran['host_pid']}
  assert ran['host_pid'] not in (adapter.pid,__import__('os').getpid()) and continuation['session_id']==parent
  _wait_for(lambda:(records.fold_records(s['root'])['turns'][continuation['id']].get('reply') or {}).get('status')=='completed',what='continuation reply after the adapter exited')
  import psutil
  _wait_for(lambda:not psutil.pid_exists(ran['host_pid']) or psutil.Process(ran['host_pid']).status()==psutil.STATUS_ZOMBIE,what='the return host to exit after its owned turn')
  states=[r['state'] for r in _event_rows(s,event['id'])]
  assert states.count('RESULT')==1 and states.count('CONTINUED')==1 and states[-1]=='CONTINUED' and len(turns())==1,states
  assert records.fold_records(s['root'])['turns'][continuation['id']]['source_admission_id']==X._ident('SA-',[account['commission_id'],'CONT-'+event['id']])
  standing=X.status(s['root'],account);assert (standing['app_admissions'],standing['sessions'])==(3,2),standing
  WD.recover(s['root'],'public',{'event_id':event['id']},{'origin':'human'})
  assert [r['state'] for r in _event_rows(s,event['id'])]==states and len(turns())==1 and len(launches)==1
 finally:
  if adapter.poll() is None:adapter.kill();adapter.wait(timeout=5)
  if host:
   import psutil
   try:psutil.Process(host['pid']).kill()
   except psutil.Error:pass


def test_detached_return_host_entry_refuses_unbanked_or_foreign_returns(source,monkeypatch):
 """The return host can only replay: a continuation reservation the return never banked, a request that is not this
 event's CONT request in its original parent session, and an unsettled event all refuse without new accounting."""
 from laplace.writing import turn_execution as T
 from laplace.work import work_delivery as WD
 s=source;grant,account,handoff=_detached_setup(s);launches=[]
 _codex_runtime(monkeypatch,launches)
 event=WD.submit(s['root'],'public',{'action':'submit','work_id':'work','expected_work_revision':W._task_revision(W._tasks('public',s['root'])['work']),'handoff_id':handoff,'obligation_id':'source','recipient_binding_id':s['binding']['id'],'parent_return':{'admit_idle':True,'max_attempts':1,'max_depth':1}},{'origin':'native','turn_id':'WT-allowance'})['event']
 request={'project':'public','session_id':s['parent']['id'],'mode':'work','text':'return','request_id':'CONT-'+event['id']}
 with pytest.raises(ValueError,match='original settled Work event'):WD.start_source_return(s['root'],'public',event['id'],request)   # still ADMITTED
 [review]=launches;original=WD._return_to_parent
 monkeypatch.setattr(WD,'_return_to_parent',lambda *a,**k:None)
 T._bank_reply(review,{'status':'completed','text':'controlled'})
 monkeypatch.setattr(WD,'_return_to_parent',original)
 assert _event_rows(s,event['id'])[-1]['state']=='RESULT'
 before=X.status(s['root'],account)['app_admissions']
 with pytest.raises(X.AllowanceRefused,match='reservation unavailable'):WD.start_source_return(s['root'],'public',event['id'],request)   # never banked
 for wrong in [{'request_id':event['id']},{'session_id':s['review']['id']},{'mode':'review'},{'project':'another'}]:
  with pytest.raises(ValueError,match='original settled Work event'):WD.start_source_return(s['root'],'public',event['id'],{**request,**wrong})
 assert X.status(s['root'],account)['app_admissions']==before and len(launches)==1
 T._finish(review,{'status':'completed'})


def test_opted_basis_never_downgrades_unattached_delivery_but_legacy_remains(source):
 s=source;grant,a,_=attached(s)
 for parent in [None,'WT-parent']:
  with pytest.raises(X.AllowanceRefused,match='trusted original'):
   X.inherit_delivery(s['root'],'public',parent,{'grant_id':grant['id']},s['binding'])
 assert X.inherit_delivery(s['root'],'public','WT-parent',{'grant_id':s['grant']['id']},s['binding']) is None
