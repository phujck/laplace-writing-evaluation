"""Actual public admission/WD/stop consumers; no real provider executable or inference."""
import copy
import json
import threading
import time
from pathlib import Path
import pytest
from laplace.work import project_work as W, development_source as D, work_delivery as WD
from laplace.writing import records, provider, turn_admission as A, turn_execution as X, turn_jobs, child_hosts
from laplace.native import tools
from test_source_use_joins import source
from test_work_review_source_basis_actual import guard


@pytest.fixture
def bound(source, monkeypatch):
    s = source; launches = []
    p = s['root']/'profiles/voice/gerard-technical-v1.md';p.parent.mkdir(parents=True);p.write_text('# Public voice\nVersion: public-v1\nBe concrete.\n')
    catalogue={'providers':[{'id':'codex','available':True,'models':[{'id':'gpt-6.1-sol','efforts':['high'],'supports_effort':True}]}]}
    monkeypatch.setattr(provider,'capabilities',lambda *a,**k:copy.deepcopy(catalogue))
    monkeypatch.setattr(provider,'context_window_advertised',lambda *a,**k:None)
    monkeypatch.setattr(X,'start',lambda launch:launches.append(launch))
    s['other']=records.index(s['root']).sessions[records.index(s['root']).turns['WT-other']['session_id']]
    s['launches']=launches
    yield s
    for launch in launches:
        if not launch.job.get('done'):X._finish(launch,{'status':'interrupted'})


def commission(s, *, native=20, apps=3, sessions=2, wall=120):
    payload={**s['payload'],'request_id':'public-allowance-grant','expected_work_revision':guard(s),
        'native_allowance':{'commission_request_id':'public-consumer-commission','max_admitted_native_invocations':native,
            'max_app_admissions':apps,'max_sessions':sessions,'wall_seconds':wall}}
    s['grant']=D.grant(s['root'],'public',payload,{'origin':'human'})['grant']
    return s['grant']


def work_fields(s):
    tasks=W._tasks('public',s['root']);basis,issue=W._work_basis(tasks,'work');assert not issue
    return {'work_id':'work','expected_work_scope_revision':basis['scope_revision'],
        'expected_dependency_revision':W._dependency_revision(tasks['work'],tasks)}


def initial(s, **extra):
    payload={'project':'public','session_id':s['parent']['id'],'mode':'work','text':'Public controlled Source commission.',
        'request_id':'public-initial-source-turn','source_grant_id':s['grant']['id'],**work_fields(s),**extra}
    return A.start_turn(s['root'],payload),payload


def source_handoff(s):
    launch=s['launches'][0];door={'origin':'native','turn_id':launch.turn_id}
    # These real backend effects prepare the public fixture; gateway counting is
    # exercised separately and no model/shell/provider bypass claim is made.
    c=D.candidate(s['root'],'public',{'grant_id':s['grant']['id'],'files':[{'path':'src/answer.py',
        'before_sha256':D._pin(s['checkout']/'src/answer.py'),'edits':[{'old':'unique old','new':'controlled new'}]}]},door)
    D.apply(s['root'],'public',{'candidate_id':c['candidate_id']},door)
    from laplace.work import project_work_review as R
    pins={p:D._pin(s['checkout']/p) for p in ['src/answer.py','evaluator.py']}
    h=R.record('public',{'id':'work','phase':'handoff','request_id':'public-allowance-handoff','expected_work_revision':guard(s),
        'obligations':['source'],'source_basis':{'grant_id':s['grant']['id'],'candidate_id':c['candidate_id']},'pins':pins},s['root'],door=door)
    return h,door


def deliver(s,h,door):
    return WD.submit(s['root'],'public',{'action':'submit','work_id':'work','expected_work_revision':guard(s),
        'handoff_id':h['phase']['id'],'obligation_id':'source','recipient_binding_id':s['binding']['id'],
        'parent_return':{'admit_idle':True,'max_attempts':1,'max_depth':1}},door)


def finish(launch,text='Public deterministic result at withheld execution boundary.'):
    result={'status':'completed','text':text};X._bank_reply(launch,result);X._finish(launch,result)


def test_initial_selector_private_attachment_snapshot_and_exact_replay(bound):
    from laplace.writing import source_execution as E
    s=bound;commission(s);result,payload=initial(s);launch=s['launches'][0]
    stored=records.fold_records(s['root'])['turns'][result['turn_id']];snapshot=copy.deepcopy(stored['source_allowance_snapshot'])
    assert stored['source_execution']==launch.source_execution==E.for_turn(s['root'],'public',launch.turn_id)
    assert snapshot['text'] in launch.prompt and 'admission-time snapshot' in snapshot['text']
    assert 'Source write authority remains separate' in snapshot['text']
    assert snapshot['text'] not in json.dumps(launch.operating_brief)
    fields={'operation':'repository','payload':{'action':'read','repository':'selected','path':'src/answer.py','limit':5}}
    tools.call(s['root'],'public','work',fields,turn_id=launch.turn_id)
    tools.call(s['root'],'public','work',fields,turn_id=launch.turn_id)
    assert E.status(s['root'],launch.source_execution)['admitted']==2
    replay=A.start_turn(s['root'],payload);assert replay['turn_id']==launch.turn_id and len(s['launches'])==1
    assert records.fold_records(s['root'])['turns'][launch.turn_id]['source_allowance_snapshot']==snapshot
    assert E.status(s['root'],launch.source_execution)['app_admissions']==1
    for changed in [{'source_grant_id':'different'},{'session_id':s['other']['id']}]:
        with pytest.raises(ValueError):A.start_turn(s['root'],{**payload,**changed})
    (s['root']/'initial-allowance-proof.json').write_text(json.dumps({'admission':result,'turn':stored,'snapshot':snapshot,
        'current':E.status(s['root'],launch.source_execution),'qualification':'Real admission and native reads; execution start withheld'},indent=2)+'\n')


def test_selector_spoofing_and_unbound_opted_in_source_refuse_without_launch(bound):
    s=bound;commission(s);before=len(records.index(s['root']).sessions)
    for field in ['source_execution','source_reservation','source_admission_id','source_control','native_allowance','max_sessions']:
        with pytest.raises(ValueError):A.start_turn(s['root'],{'project':'public','text':'no','source_grant_id':s['grant']['id'],field:{}})
    for extra in [{'session_id':''},{'session_id':s['review']['id']},{'mode':'review'}]:
        with pytest.raises(ValueError):initial(s,**extra)
    with pytest.raises(ValueError):
        A.start_turn(s['root'],{'project':'public','text':'no','mode':'work','session_id':s['parent']['id'],
            'source_grant_id':s['grant']['id'],**work_fields(s)},dispatch={'dispatch_id':'not-a-commission'})
    with pytest.raises(ValueError):D.read(s['root'],'public',{'grant_id':s['grant']['id'],'path':'src/answer.py'},s['door'])
    assert not s['launches'] and len(records.index(s['root']).sessions)==before


def test_reviewer_and_original_parent_share_reservations_and_historical_turn_identity(bound):
    from laplace.writing import source_execution as E
    s=bound;commission(s);initial(s);h,door=source_handoff(s);result=deliver(s,h,door);event=result['event']
    assert event['state']=='ADMITTED' and len(s['launches'])==2
    parent,review=s['launches'];account=parent.source_execution
    assert review.source_execution==account and E.for_turn(s['root'],'public',review.turn_id)==account
    finish(parent)
    tools.execute(s['root'],'public','review','work_review',{'id':'work','phase':'review','request_id':'public-allowance-verdict',
        'expected_work_revision':guard(s),'handoff_id':h['phase']['id'],'obligation_id':'source','verdict':'ACCEPT'},turn_id=review.turn_id)
    finish(review)
    current=WD.status(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']
    assert current['state']=='CONTINUED' and len(s['launches'])==3
    continuation=s['launches'][2];assert continuation.session_id==s['parent']['id'] and continuation.source_execution==account
    assert E.for_turn(s['root'],'public',parent.turn_id)==account  # not session's latest admission ID
    assert E.for_turn(s['root'],'public',continuation.turn_id)==account
    state=E.status(s['root'],account);assert state['app_admissions']==3 and state['sessions']==2
    assert WD.recover(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']['id']==event['id'] and len(s['launches'])==3
    (s['root']/'shared-delivery-allowance-proof.json').write_text(json.dumps({'event':current,'standing':state,
        'turn_ids':[l.turn_id for l in s['launches']],'qualification':'Real owner/admission/terminal flow; all3execution starts withheld, deterministic replies'},indent=2)+'\n')


def test_exhaustion_keeps_worker_verdict_and_refuses_automatic_parent(bound):
    from laplace.writing import source_execution as E
    s=bound;commission(s,native=1);initial(s);h,door=source_handoff(s);event=deliver(s,h,door)['event'];parent,review=s['launches'];finish(parent)
    tools.execute(s['root'],'public','review','work_review',{'id':'work','phase':'review','request_id':'public-final-slot-verdict',
        'expected_work_revision':guard(s),'handoff_id':h['phase']['id'],'obligation_id':'source','verdict':'ACCEPT'},turn_id=review.turn_id)
    assert E.status(s['root'],parent.source_execution)['remaining']==0
    finish(review)
    current=WD.status(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']
    assert current['state']=='PARENT_REFUSED' and 'Source allowance' in current['reason'] and len(s['launches'])==2
    assert current['acceptance']['satisfied'] and current['admitted']['recipient_ack']=='TERMINAL'
    (s['root']/'exhausted-parent-proof.json').write_text(json.dumps(current,indent=2)+'\n')


def test_lost_session_and_turn_ack_reconcile_without_duplicate_reservations(bound,monkeypatch):
    from laplace.writing import source_execution as E
    s=bound;commission(s);initial(s);h,door=source_handoff(s);real_bank=records.bank;once=[]
    def bank(root,row):
        out=real_bank(root,row)
        if row.get('record')=='writing-session' and row.get('role')=='review' and row.get('source_admission_id') and not once:
            once.append(row['id']);raise RuntimeError('public session acknowledgement lost')
        return out
    monkeypatch.setattr(records,'bank',bank)
    event=deliver(s,h,door)['event'];assert event['state']=='SUBMITTED' and once and len(s['launches'])==1
    monkeypatch.setattr(records,'bank',real_bank)
    real_append=W._append
    def append(root,row):
        if row.get('kind')==WD.EVENT and row.get('state')=='ADMITTED':raise RuntimeError('public turn acknowledgement lost')
        return real_append(root,row)
    monkeypatch.setattr(W,'_append',append)
    with pytest.raises(RuntimeError,match='turn acknowledgement'):
        WD.recover(s['root'],'public',{'event_id':event['id']},{'origin':'human'})
    monkeypatch.setattr(W,'_append',real_append)
    current=WD.recover(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']
    assert current['state']=='ADMITTED' and current['admitted']['session_id']==once[0] and len(s['launches'])==2
    state=E.status(s['root'],s['launches'][0].source_execution);assert state['app_admissions']==2 and state['sessions']==2
    (s['root']/'admission-ack-recovery-proof.json').write_text(json.dumps({'event':current,'standing':state},indent=2)+'\n')


def test_unsupported_generic_dispatch_refuses_before_reservation_and_legacy_stays_local(bound,monkeypatch):
    from laplace.writing import dispatch_execution as G, dispatch_parent, workflow_dispatch
    from types import SimpleNamespace
    s=bound;commission(s);initial(s);parent=s['launches'][0];before=len(records.index(s['root']).sessions)
    reached=[]
    # Keep the existing dispatch's parent/plan validation seam; no packets or
    # reservation are synthesized. The reached Source check precedes plan work.
    monkeypatch.setattr(G,'_dispatch_row',lambda *a,**k:{'plan':{},'row':{},'plan_file':None,'parent_provider':'codex'})
    def plan(*a):reached.append('plan');raise ValueError('legacy reached plan validation')
    monkeypatch.setattr(G,'_plan_shape',plan)
    with pytest.raises(ValueError,match='unsupported generic'):
        G.launch_dispatch(s['root'],'public',parent.turn_id,{'id':'public-dispatch'})
    assert not reached
    with pytest.raises(ValueError,match='legacy reached'):
        G.launch_dispatch(s['root'],'public','WT-other',{'id':'public-dispatch'})
    assert reached==['plan']
    with pytest.raises(ValueError,match='legacy reached'):
        G.launch_dispatch(s['root'],'public',parent.turn_id,{'id':'public-dispatch'},validate_only=True)
    monkeypatch.setattr(G,'_continuation_task',lambda *a:{'id':'public-dispatch'})
    monkeypatch.setattr(dispatch_parent,'parent_actor',lambda *a:True)
    monkeypatch.setattr(workflow_dispatch,'_definitions',lambda:SimpleNamespace(native_caller=lambda *a:{}))
    monkeypatch.setattr(workflow_dispatch,'_admit',lambda *a:None)
    monkeypatch.setattr(G,'_continuation_basis',lambda *a:pytest.fail('no continuation reservation may be prepared'))
    with pytest.raises(ValueError,match='unsupported generic'):
        G.continue_dispatch(s['root'],'public',parent.turn_id,
            {'id':'public-dispatch','packet':'p','request_id':'public-continue','guard':{},'budget':{}})
    with pytest.raises(ValueError,match='unsupported generic'):
        A.start_turn(s['root'],{'project':'public','session_id':s['review']['id'],'text':'no child'},
            dispatch={'dispatch_id':'public-dispatch','parent_turn_id':parent.turn_id})
    assert len(records.index(s['root']).sessions)==before and len(s['launches'])==1
    (s['root']/'unsupported-spawn-proof.json').write_text(json.dumps({'reached':reached,'sessions':before,
        'qualification':'Actual Source parent and direct dispatch entry gates; existing dispatch validation stages are isolated, no packet/session/effect reservation.'},indent=2)+'\n')


def _codex_callback(s,turn_id):
    """Compile the actual nested native adapter callback without starting a CLI."""
    import ast
    from types import SimpleNamespace
    tree=ast.parse(Path(provider.__file__).read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='WritingTurn')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_codex')
    callback=next(n for n in method.body if isinstance(n,ast.FunctionDef) and n.name=='tool_call')
    namespace={'self':SimpleNamespace(cwd=s['root'],project='public',mode='work',logical_turn_id=turn_id,native_id='public-native',event=lambda x:None),
        'ProviderError':provider.ProviderError,'json':json,'writing_operating_door':provider.writing_operating_door}
    exec(compile(ast.Module(body=[callback],type_ignores=[]),provider.__file__,'exec'),namespace)
    return namespace['tool_call']


def _rpc_arrival(monkeypatch,callback,fields,*,encode_failure=False,send_failure=False,on_send=None):
    import io
    from types import SimpleNamespace
    from laplace.projects import writing_sources
    from laplace.writing import delivery
    threads=[];sent=[];uncertain=[];local=threading.local();real_thread=threading.Thread
    real_items=writing_sources.content_items;real_uncertain=delivery.delivery_uncertain
    def thread(*a,**k):
        t=real_thread(*a,**k);threads.append(t);return t
    def call(*a,**k):
        out=callback(*a,**k);local.returned=True;return out
    def items(*a,**k):
        if encode_failure and getattr(local,'returned',False):raise ValueError('public outer encoding failure')
        return real_items(*a,**k)
    def uncertain_call(holder):uncertain.append(True);return real_uncertain(holder)
    def send(value):
        if on_send:on_send(value)
        sent.append(value)
        if send_failure:raise provider.ProviderError('public send failure')
    conn=object.__new__(provider._CodexRpcConnection)
    conn.process=SimpleNamespace(stdout=io.StringIO(json.dumps({'id':'SAME-RPC-ID','method':'item/tool/call',
        'params':{'tool':provider.writing_operating_door(),'threadId':'public-native','arguments':fields}})+'\n'))
    conn.native_tool_calls=True;conn.tool_handler=call;conn.lock=threading.Lock();conn.pending={};conn.event=lambda x:None;conn.send=send
    with monkeypatch.context() as m:
        m.setattr(provider.threading,'Thread',thread);m.setattr(writing_sources,'content_items',items);m.setattr(delivery,'delivery_uncertain',uncertain_call)
        conn._read()
        for t in threads:t.join(timeout=5);assert not t.is_alive()
    assert len(sent)==1
    return {'response':sent[0],'uncertainty_calls':len(uncertain)}


def test_codex_actual_callback_invalid_shapes_repeated_rpc_and_outer_uncertainty(bound,monkeypatch):
    from laplace.writing import source_execution as E
    s=bound;commission(s,native=20);initial(s);launch=s['launches'][0];callback=_codex_callback(s,launch.turn_id)
    fields={'operation':'repository','payload':{'action':'read','repository':'selected','path':'src/answer.py','limit':5}}
    outputs=[]
    for shape in [fields,fields,None,[],7]:outputs.append(_rpc_arrival(monkeypatch,callback,shape))
    assert E.status(s['root'],launch.source_execution)['admitted']==5
    assert all(not x['uncertainty_calls'] for x in outputs)
    assert outputs[0]['response']['result']['success'] and outputs[1]['response']['result']['success']
    assert all(not x['response']['result']['success'] for x in outputs[2:])
    # The same request id does not deduplicate arrivals. Encoding/send errors
    # after a real owner result settle that same spent native claim.
    outputs.append(_rpc_arrival(monkeypatch,callback,fields,encode_failure=True))
    assert outputs[-1]['uncertainty_calls']==1 and E.status(s['root'],launch.source_execution)['admitted']==6
    outputs.append(_rpc_arrival(monkeypatch,callback,fields,send_failure=True))
    assert outputs[-1]['uncertainty_calls']==1 and E.status(s['root'],launch.source_execution)['admitted']==7
    outcomes=[r for r in records.source_execution_metadata(s['root'],'public',launch.source_execution['commission_id'])[1]
        if r['record']=='writing-native-call-outcome']
    assert sum(r['state']=='DELIVERY_UNCERTAIN' for r in outcomes)==2
    (s['root']/'codex-incoming-proof.json').write_text(json.dumps({'outputs':outputs,'standing':E.status(s['root'],launch.source_execution),
        'outcomes':outcomes,'qualification':'Actual RPC reader/thread and compiled original callback; fake stdout/send only, no App Server executable'},indent=2)+'\n')


def test_actual_owned_child_wall_stop_reaps_and_keeps_partial(bound,monkeypatch):
    import os,subprocess,sys
    from test_writing_dispatch import _StubTurn
    from laplace.writing import source_execution as E
    s=bound;commission(s,wall=3);initial(s);launch=s['launches'][0]
    helper=Path(os.environ['SOURCE_ALLOWANCE_PROCESS_HELPER'])
    helper.write_text("import signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nprint('ready',flush=True)\ntime.sleep(30)\n")
    children=[];interrupts=[]
    class ControlledTurn(_StubTurn):
        def run(self,prompt):
            self.inference_started=True;self.emit({'type':'delta','text':'Public partial Source result Ω.'})
            self.process=subprocess.Popen([sys.executable,'-S',str(helper)],stdout=subprocess.PIPE,text=True)
            children.append(self.process);self.on_spawn(self.process,'synthetic-source-wall')
            assert self.process.stdout.readline().strip()=='ready'
            self.process.wait(timeout=12)
            return {'status':'interrupted','text':'Public partial Source result Ω.'}
        def interrupt(self):interrupts.append(True) # registered process owner must do TERM/KILL
    monkeypatch.setattr(provider,'WritingTurn',ControlledTurn)
    started=time.monotonic();X.run(launch)
    assert launch.job['done'] and children and children[0].poll() is not None and interrupts
    reply=records.fold_records(s['root'])['turns'][launch.turn_id]['reply'];execution=child_hosts._child_execution_record(s['root'],launch.session_id)
    assert reply['status']=='interrupted' and reply['text']=='Public partial Source result Ω.'
    assert reply['source_allowance']['state']=='STOPPED' and time.monotonic()-started<12
    assert all(not child_hosts._process_matches(p) for p in execution['provider_processes'])
    with pytest.raises(ValueError):E.reserve_app(s['root'],launch.source_execution,'after-stop',session_id=launch.session_id)
    (s['root']/'source-wall-stop-proof.json').write_text(json.dumps({'reply':reply,'execution':execution,
        'processes':[{'pid':p.pid,'returncode':p.returncode} for p in children],'interrupts':len(interrupts),'elapsed':time.monotonic()-started,
        'qualification':'One exact public harmless Python child; no provider. In-process Python owner effects are not claimed killed or rolled back.'},indent=2)+'\n')


def test_unbound_legacy_admission_and_generic_rpc_remain_unattached(bound,monkeypatch):
    import io
    from types import SimpleNamespace
    from laplace.writing import source_execution as E
    s=bound
    started=A.start_turn(s['root'],{'project':'public','session_id':s['parent']['id'],'mode':'work',
        'text':'Public ordinary legacy turn.','request_id':'public-legacy-turn',**work_fields(s)})
    launch=s['launches'][0];assert not launch.source_execution and E.for_turn(s['root'],'public',launch.turn_id) is None
    assert 'source_execution' not in records.index(s['root']).turns[started['turn_id']]
    assert 'Source allowance (admission-time snapshot)' not in launch.prompt
    received=[];threads=[];real_thread=threading.Thread
    def thread(*a,**k):t=real_thread(*a,**k);threads.append(t);return t
    conn=object.__new__(provider._CodexRpcConnection)
    conn.process=SimpleNamespace(stdout=io.StringIO(json.dumps({'id':1,'method':'item/tool/call','params':{'x':1}})+'\n'))
    conn.native_tool_calls=False;conn.tool_handler=lambda params:({'legacy':params})
    conn.lock=threading.Lock();conn.pending={};conn.event=lambda x:None;conn.send=received.append
    with monkeypatch.context() as m:
        m.setattr(provider.threading,'Thread',thread);conn._read()
        for t in threads:t.join(timeout=3);assert not t.is_alive()
    assert len(received)==1 and received[0]['result']['success']


def test_reader_fingerprint_consequence_is_passive_and_unqualified(bound):
    from laplace.writing import sealed_reader
    from laplace.projects.writing_sources import file_revision
    s=bound
    value=sealed_reader.support(s['root'],'public')
    assert value['state']!='QUALIFIED'
    (s['root']/'reader-fingerprint-consequence.json').write_text(json.dumps({'support':value,
        'changed_components':{name:file_revision(Path(provider.__file__).with_name(name)) for name in ['provider.py','turn_execution.py']},
        'qualification':'Passive fresh public support lookup and executable hash only. No CLI, operator proof or canary; existing host proof is untouched and cannot qualify changed source fingerprint.'},indent=2)+'\n')


def test_codex_last_slot_delivers_before_supervisor_can_stop(bound,monkeypatch):
    from laplace.writing import source_execution as E
    s=bound;commission(s,native=1);initial(s);launch=s['launches'][0];during=[]
    fields={'operation':'repository','payload':{'action':'read','repository':'selected','path':'src/answer.py','limit':5}}
    out=_rpc_arrival(monkeypatch,_codex_callback(s,launch.turn_id),fields,
        on_send=lambda value:during.append(E.control(s['root'],'public',launch.turn_id)))
    assert out['response']['result']['success'] and len(during)==1
    assert during[0]['remaining']==0 and during[0]['active_for_turn']==1 and not during[0]['stop']
    after=E.control(s['root'],'public',launch.turn_id)
    assert after['active_for_turn']==0 and after['stop']
    (s['root']/'codex-final-slot-send-proof.json').write_text(json.dumps({'during_send':during[0],'after_send':after,'response':out,
        'qualification':'Actual Codex RPC incoming context/callback/outer sender with synthetic stdout/send; no provider process'},indent=2)+'\n')


class _OneControlIteration:
    def __init__(self):self.once=False
    def wait(self,_timeout):
        if self.once:return True
        self.once=True;return False


def test_shared_final_delivery_survives_other_turn_governor_and_finish(bound):
    from laplace.writing import source_execution as E,delivery
    from types import SimpleNamespace
    s=bound;commission(s,native=1);initial(s);h,door=source_handoff(s);deliver(s,h,door);parent,review=s['launches']
    interruptions=[];peer_provider=SimpleNamespace(interrupt=lambda:interruptions.append('peer'))
    with delivery.incoming() as holder:
        E.claim_native(s['root'],'public',review.turn_id,holder,{'public':'final response encoding'})
        before=E.control(s['root'],'public',review.turn_id)
        # Replay the original parent-governor consequence, then the same local
        # interruption/finalization consequence that previously wrote Stop.
        X._govern(parent,None,_OneControlIteration(),[],{})
        after_govern=E.control(s['root'],'public',review.turn_id)
        assert not parent.job.get('interrupt_requested') and not after_govern['stop']
        parent.job['interrupt_requested']=True
        X._govern(parent,None,_OneControlIteration(),[],{})
        X._finish(parent,{'status':'interrupted'})
        after_finish=E.control(s['root'],'public',review.turn_id)
        assert parent.job['source_interrupt_scope']=='turn' and after_finish['active']==1 and not after_finish['stop']
        assert after_finish['state']=='DRAINING'
        E.settle_native(s['root'],holder,'SETTLED_SUCCESS')
        assert not E.control(s['root'],'public',review.turn_id)['stop']
    settled=E.control(s['root'],'public',review.turn_id);assert settled['active']==0 and settled['stop']
    X._govern(review,peer_provider,_OneControlIteration(),[],{})
    X._finish(review,{'status':'interrupted'})
    assert interruptions==['peer'] and review.job['source_interrupt_scope']=='commission'
    assert E.status(s['root'],review.source_execution)['state']=='STOPPED'
    (s['root']/'shared-drain-govern-finish-proof.json').write_text(json.dumps({'before':before,'after_govern':after_govern,
        'after_local_finish':after_finish,'after_last_send':settled,'final':E.status(s['root'],review.source_execution),
        'parent_scope':parent.job['source_interrupt_scope'],'review_scope':review.job['source_interrupt_scope'],
        'qualification':'Real shared parent/reviewer admissions, original governor and finalizer; one synthetic admitted claim/outer delivery, execution withheld.'},indent=2)+'\n')


@pytest.mark.parametrize('selected',['parent','reviewer'])
def test_author_selected_turn_stop_is_local_and_stopped_parent_never_restarts(bound,selected):
    from laplace.writing import source_execution as E,delivery,turn_control
    s=bound;commission(s,native=4);initial(s);h,door=source_handoff(s)
    event=WD.submit(s['root'],'public',{'action':'submit','work_id':'work','expected_work_revision':guard(s),
        'handoff_id':h['phase']['id'],'obligation_id':'source','recipient_binding_id':s['binding']['id'],
        'parent_return':{'admit_idle':selected=='parent','max_attempts':1,'max_depth':1}},door)['event']
    parent,review=s['launches'];target,peer=(parent,review) if selected=='parent' else (review,parent)
    with delivery.incoming() as holder:
        E.claim_native(s['root'],'public',peer.turn_id,holder,{'public':'peer admitted response'})
        stopped=turn_control.interrupt_turn(s['root'],{'project':'public','turn_id':target.turn_id})
        assert stopped['turn_ids']==[target.turn_id]
        X._govern(target,None,_OneControlIteration(),[],{})
        result={'status':'interrupted','text':'Public selected-turn author Stop.'}
        X._bank_reply(target,result);X._finish(target,result)
        during=E.control(s['root'],'public',peer.turn_id)
        assert target.job['source_interrupt_scope']=='turn' and during['state']=='ACTIVE' and not during['stop']
        E.settle_native(s['root'],holder,'SETTLED_SUCCESS')
    if selected=='parent':
        tools.execute(s['root'],'public','review','work_review',{'id':'work','phase':'review','request_id':'public-local-stop-verdict',
            'expected_work_revision':guard(s),'handoff_id':h['phase']['id'],'obligation_id':'source','verdict':'ACCEPT'},turn_id=review.turn_id)
        finish(review)
        final_event=WD.status(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']
        assert final_event['state']=='PARENT_REFUSED' and 'stopped' in final_event['reason'] and final_event['acceptance']['satisfied']
        assert len(s['launches'])==2
    else:final_event=WD.status(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']
    assert E.status(s['root'],target.source_execution)['state']=='ACTIVE'
    (s['root']/'selected-turn-local-stop-proof.json').write_text(json.dumps({'selected':selected,'actual_stop':stopped,
        'peer_during_stop':during,'standing':E.status(s['root'],target.source_execution),'event':final_event,
        'qualification':'Actual selected-turn Stop/governor/reply/finalizer; peer synthetic admitted claim; model execution withheld.'},indent=2)+'\n')


@pytest.mark.parametrize('cause',['deadline','explicit-account-stop','unknown'])
def test_account_deadline_explicit_stop_and_unknown_interrupt_even_active_peer(bound,monkeypatch,cause):
    import datetime as dt
    from laplace.writing import source_execution as E,delivery
    from types import SimpleNamespace
    s=bound;commission(s,native=1);initial(s);h,door=source_handoff(s);deliver(s,h,door);parent,review=s['launches'];interruptions=[]
    p=SimpleNamespace(interrupt=lambda:interruptions.append(True))
    with delivery.incoming() as holder:
        E.claim_native(s['root'],'public',review.turn_id,holder,{'public':'still active admitted response'})
        with monkeypatch.context() as m:
            if cause=='deadline':
                deadline=dt.datetime.fromisoformat(E.status(s['root'],review.source_execution)['deadline_at'])
                m.setattr(E,'_now',lambda:deadline+dt.timedelta(seconds=1))
            elif cause=='explicit-account-stop':E.stop(s['root'],parent.source_execution,'PUBLIC_EXPLICIT_ACCOUNT_STOP')
            else:
                def unavailable(*a,**k):raise OSError('public metadata read unavailable')
                m.setattr(records,'source_execution_metadata',unavailable)
            before=E.control(s['root'],'public',review.turn_id);assert before['stop']
            X._govern(parent,p,_OneControlIteration(),[],{})
            X._finish(parent,{'status':'interrupted'})
            assert interruptions==[True] and parent.job['source_interrupt_scope']=='commission'
            after=E.control(s['root'],'public',review.turn_id);assert after['stop']
        # Account Stop does not erase this in-process claim or manufacture a
        # cancelled/rolled-back owner effect. It may still settle truthfully.
        E.settle_native(s['root'],holder,'SETTLED_SUCCESS')
    standing=E.status(s['root'],review.source_execution);assert standing['admitted']==1 and standing['active']==0 and standing['state']=='STOPPED'
    (s['root']/'shared-immediate-stop-proof.json').write_text(json.dumps({'cause':cause,'before':before,'after':after,
        'final':standing,'interruptions':len(interruptions),'qualification':'Actual governor/finalizer, one synthetic admitted claim, deterministic clock/read outage or explicit owner Stop; no provider process/rollback claim.'},indent=2)+'\n')


def _ordinary_handoff(s,turn_id):
    from laplace.work import project_work_review as R
    path=s['root']/'guide.md';path.write_text('A public ordinary Work review guide.\n')
    return R.record('public',{'id':'work','phase':'handoff','request_id':'public-ordinary-guide-handoff',
        'expected_work_revision':guard(s),'obligations':['guide'],'pins':{'guide.md':D._pin(path)}},
        s['root'],door={'origin':'native','turn_id':turn_id})


def _ordinary_delivery_wire(s,h,*,obligation='guide'):
    return {'action':'submit','work_id':'work','expected_work_revision':guard(s),
        'handoff_id':h['phase']['id'],'obligation_id':obligation,'recipient_binding_id':s['binding']['id'],
        'parent_return':{'admit_idle':True,'max_attempts':1,'max_depth':1}}


def _historical_pending(s,monkeypatch,*,typed=False):
    """Public old-shape fixture only; current recovery runs with no bypass.

    Bypass ONLY the new submit-origin check and withhold transport to construct
    a previously retained SUBMITTED intent. This is not permission for a new
    admission or evidence that the corrected submit would accept this intent.
    """
    parent=s['launches'][0]
    h,_=source_handoff(s) if typed else (_ordinary_handoff(s,parent.turn_id),None)
    with monkeypatch.context() as m:
        m.setattr(WD,'_source_origin',lambda *a,**k:None)
        m.setattr(WD,'_deliver',lambda *a:None)
        event=WD.submit(s['root'],'public',_ordinary_delivery_wire(s,h,obligation='source' if typed else 'guide'),
            {'origin':'native','turn_id':parent.turn_id})['event']
    assert event['state']=='SUBMITTED' and 'source_execution' not in event
    return event


def test_source_native_plain_submit_refuses_before_any_resumable_intent(bound):
    from laplace.writing import source_execution as E
    s=bound;commission(s);initial(s);parent=s['launches'][0];h=_ordinary_handoff(s,parent.turn_id)
    before=copy.deepcopy(E.status(s['root'],parent.source_execution));sessions=len(records.index(s['root']).sessions)
    with pytest.raises(ValueError,match='Source-bound delivery requires') as caught:
        tools.execute(s['root'],'public','work','work_delivery',_ordinary_delivery_wire(s,h),turn_id=parent.turn_id)
    events=WD._rows(W._tasks('public',s['root'])['work'],WD.EVENT)
    after=E.status(s['root'],parent.source_execution)
    assert events==[] and len(s['launches'])==1 and len(records.index(s['root']).sessions)==sessions
    assert after['app_admissions']==before['app_admissions']==1 and after['sessions']==before['sessions']==1
    assert after['admitted']==before['admitted']+1  # refused native call still spends its own slot
    (s['root']/'plain-new-submit-proof.json').write_text(json.dumps({'error':str(caught.value),'events':events,
        'before':before,'after':after,'sessions':sessions,'qualification':'Original actual native Source-bound ordinary submit counterexample now refuses before Work event/transport; no model execution.'},indent=2)+'\n')


@pytest.mark.parametrize('typed',[False,True])
def test_stored_source_origin_pending_cannot_recover_new_unbound_reviewer(bound,monkeypatch,typed):
    from laplace.writing import source_execution as E
    s=bound;commission(s);initial(s);parent=s['launches'][0];event=_historical_pending(s,monkeypatch,typed=typed)
    before=copy.deepcopy(E.status(s['root'],parent.source_execution));sessions=len(records.index(s['root']).sessions)
    value=WD.recover(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']
    assert value['state']=='STALE' and ('Source-bound delivery' in value['reason'] or 'Source execution attachment' in value['reason'])
    assert len(s['launches'])==1 and len(records.index(s['root']).sessions)==sessions
    assert E.status(s['root'],parent.source_execution)==before
    assert WD.recover(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']['state']=='STALE'
    (s['root']/'stored-source-pending-proof.json').write_text(json.dumps({'typed_basis':typed,'original_pending':event,
        'recovery':value,'account':before,'sessions':sessions,'qualification':'Explicit historical SUBMITTED seed bypasses new-submit check only; actual current human recovery has no bypass and creates no session/WT.'},indent=2)+'\n')


def _historical_reviewer(s,event):
    """Actual independent WT for an already-existing historical effect fixture."""
    return A.start_turn(s['root'],{'project':'public','session_id':s['review']['id'],'mode':'review',
        'request_id':event['id'],'text':'Public historical reviewer already admitted outside the Source commission.'})


def test_historical_unbound_reviewer_reconciles_first_but_cannot_start_new_parent(bound,monkeypatch):
    from laplace.writing import source_execution as E
    s=bound;commission(s);initial(s);parent=s['launches'][0];event=_historical_pending(s,monkeypatch)
    admitted=_historical_reviewer(s,event);review=s['launches'][1];assert review.source_execution is None
    before=copy.deepcopy(E.status(s['root'],parent.source_execution));sessions=len(records.index(s['root']).sessions)
    # Direct deliver and the public recover both reconcile the actual WT first;
    # neither upgrades its absent execution attachment or charges it retroactively.
    WD._deliver(s['root'],'public',event['id'])
    recovered=WD.recover(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']
    assert recovered['admitted']['turn_id']==admitted['turn_id'] and recovered['admitted']['recovered']
    assert 'source_execution' not in recovered and len(s['launches'])==2
    finish(parent);finish(review)
    result=WD.status(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']
    assert result['state']=='PARENT_REFUSED' and 'Source-bound delivery' in result['reason']
    assert result['admitted']['turn_id']==admitted['turn_id'] and result['admitted']['recipient_ack']=='TERMINAL'
    assert len(s['launches'])==2 and len(records.index(s['root']).sessions)==sessions
    assert E.status(s['root'],parent.source_execution)==before
    (s['root']/'historical-review-reconcile-proof.json').write_text(json.dumps({'historical_admission':admitted,
        'recovered':recovered,'after_result':result,'account':before,
        'qualification':'Public historical pending/independent unbound WT fixture; real direct/recover reconciliation and terminal hook refuse a NEW parent. No retroactive Source coverage/admission or model run.'},indent=2)+'\n')


def test_historical_continuation_reconciles_first_without_new_coverage_or_charge(bound,monkeypatch):
    from laplace.writing import source_execution as E
    s=bound;commission(s);initial(s);parent=s['launches'][0];event=_historical_pending(s,monkeypatch)
    review_admitted=_historical_reviewer(s,event);review=s['launches'][1];WD._deliver(s['root'],'public',event['id']);finish(parent)
    continuation=A.start_turn(s['root'],{'project':'public','session_id':parent.session_id,'mode':'work',
        'request_id':'CONT-'+event['id'],'text':'Public historical continuation already admitted outside Source.'})
    assert s['launches'][2].source_execution is None
    before=copy.deepcopy(E.status(s['root'],parent.source_execution));finish(review)
    value=WD.recover(s['root'],'public',{'event_id':event['id']},{'origin':'human'})['event']
    assert value['state']=='CONTINUED' and value['parent_return']['continuation_turn']['turn_id']==continuation['turn_id']
    assert 'source_execution' not in value and len(s['launches'])==3 and E.status(s['root'],parent.source_execution)==before
    (s['root']/'historical-cont-reconcile-proof.json').write_text(json.dumps({'historical_reviewer':review_admitted,
        'historical_continuation':continuation,'recovery':value,'account':before,
        'qualification':'Public old pending and actual existing unbound WT/CONT fixture; current terminal/recovery follows existing identities first, no NEW admission/Source coverage claim.'},indent=2)+'\n')


def test_true_legacy_plain_delivery_still_admits_and_recovers_once(bound):
    s=bound;h=_ordinary_handoff(s,'WT-parent')
    value=WD.submit(s['root'],'public',_ordinary_delivery_wire(s,h),{'origin':'native','turn_id':'WT-parent'})['event']
    assert value['state']=='ADMITTED' and 'source_execution' not in value and len(s['launches'])==1
    assert s['launches'][0].source_execution is None
    again=WD.recover(s['root'],'public',{'event_id':value['id']},{'origin':'human'})['event']
    assert again['admitted']['turn_id']==value['admitted']['turn_id'] and len(s['launches'])==1
    (s['root']/'legacy-durable-origin-proof.json').write_text(json.dumps({'event':value,'recovered':again,
        'qualification':'Real absent-policy legacy Work delivery/admission/recovery; execution withheld.'},indent=2)+'\n')


def test_typed_source_origin_still_admits_original_evaluator(bound):
    from laplace.writing import source_execution as E
    s=bound;commission(s);initial(s);h,door=source_handoff(s);value=deliver(s,h,door)['event']
    assert value['state']=='ADMITTED' and len(s['launches'])==2
    assert value['source_execution']==s['launches'][0].source_execution==s['launches'][1].source_execution
    assert E.status(s['root'],s['launches'][0].source_execution)['app_admissions']==2
    (s['root']/'typed-durable-origin-proof.json').write_text(json.dumps({'event':value,
        'account':E.status(s['root'],s['launches'][0].source_execution),'qualification':'Affected supported typed Source delivery uses actual original evaluator and same account; execution withheld.'},indent=2)+'\n')
