"""Ordered, exact addressed controls over the existing owner and small owned fixtures."""
from __future__ import annotations
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
import pytest
from laplace.web import authoring as owner
from laplace.native import tools as writing_tools
from laplace.writing import child_hosts
from laplace.writing import turn_admission
from laplace.writing import records as writing_records
from laplace.writing import turn_control
import uuid
from laplace.writing import session_reads
from laplace.writing.records import _fold as records_fold
from laplace.writing import turn_jobs
from laplace.writing import child_hosts, turn_control, turn_jobs
from laplace.writing import provider as writing_provider
from test_writing_dispatch import REAL_TURN, tree, _parent_turn
# Seams stand on the module whose global the code path reads (runtime fixture correction, Sol RF-2):
# turn_control._deliver_child_steering calls its own steer_turn and child_hosts._write_host/_read_host/
# _child_control_rows/_provider_controls by attribute; interrupt_turn terminates through child_hosts.
# The facade `owner` is a one-way alias and is read here for the unpatched public verbs only.


def _execution(root):
    # Pytest removes successful fixture directories and reuses their path; this is a new ledger.
    records_fold._CACHE.pop(str(root / records_fold._STORE), None)
    _, parent = _parent_turn(root)
    session = turn_admission.new_session(root, 'book', 'claude', '', '', model_role='worker',
                                dispatch_id='WORK-controls', packet='worker')
    turn = {'record':'writing-turn', 'id':'WT-control-child', 'project':'book',
            'session_id':session['id'], 'parent_turn_id':parent, 'dispatch_id':'WORK-controls',
            'provider_settings':{'provider':'codex'}, 'text':'fixture','mode':'work'}
    writing_records.bank(root, turn)
    child_hosts._update_child_execution(root, session['id'], {'session_id':session['id'],
        'project':'book','state':'RUNNING','turn_id':turn['id'], 'host':child_hosts._process_identity()})
    return turn


def _admit(root,turn,text,**extras):
    return turn_control._admit_child_steering(root,turn,{'turn_id':turn['id'],'project':'book','text':text,**extras})


def _items(root,turn,**kwargs):
    return session_reads.session_turn_detail(root,'book',turn['id'],'controls',**kwargs)['items']


def test_reversed_uuid_names_deliver_in_admission_order_and_retain_first_ack(tree,monkeypatch):
    turn=_execution(tree)
    real_uuid=uuid.uuid4
    ids=iter(['f'*32,'0'*32])
    monkeypatch.setattr(uuid,'uuid4',lambda:SimpleNamespace(hex=next(ids)))
    first=_admit(tree,turn,'First: long draft',selection={'draft':'long draft text'})
    second=_admit(tree,turn,'Second: correction, short draft',selection={'draft':'short'})
    monkeypatch.setattr(uuid,'uuid4',real_uuid)
    delivered=[]
    monkeypatch.setattr(turn_control,'steer_turn',lambda root,payload:delivered.append(dict(payload)) or {'ok':True})
    turn_control._deliver_child_steering(tree,turn['session_id'],turn['id'])
    turn_control._deliver_child_steering(tree,turn['session_id'],turn['id'])
    assert [row['text'] for row in delivered]==['First: long draft','Second: correction, short draft']
    assert [row['selection']['draft'] for row in delivered]==['long draft text','short']
    assert [first[1]['sequence'],second[1]['sequence']]==[1,2]
    assert [row['state'] for row in _items(tree,turn)]==['DELIVERED','DELIVERED']
    first_ack=_items(tree,turn,item_id=first[1]['control_id'])[0]
    assert first_ack['control_id']=='f'*32 and first_ack['sequence']==1
    assert session_reads.child_execution(tree,turn['session_id'],controls=True)['last_control']['control_id']=='0'*32
    result=writing_tools.execute(tree,'book','work','conversation_history',
        {'view':'controls','turn_id':turn['id'],'item_id':first[1]['control_id']},turn_id=turn['parent_turn_id'])
    assert result['items']==[first_ack]


def test_cross_process_admission_uses_one_monotonic_counter(tree):
    turn=_execution(tree)
    source=Path(owner.__file__).resolve().parents[2]
    env={**os.environ,'PYTHONPATH':str(source),'LAPLACE_STATE':str(tree/'state'),'LAPLACE_TEST_PROCESS':'1'}
    code='''import json,sys
from pathlib import Path
from laplace.web import authoring as a
root=Path(sys.argv[1]);turn=a._records(root)['turns'][sys.argv[2]]
request,receipt=a._admit_child_steering(root,turn,{'turn_id':turn['id'],'text':sys.argv[3]})
print(json.dumps(receipt))
'''
    def admit(index):
        result=subprocess.run([sys.executable,'-c',code,str(tree),turn['id'],str(index)],
                              env=env,cwd=tree,text=True,capture_output=True,timeout=15)
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        receipts=list(pool.map(admit,range(4)))
    assert sorted(row['sequence'] for row in receipts)==[1,2,3,4]
    assert session_reads.child_execution(tree,turn['session_id'])['control_sequence']==4
    assert len({row['control_id'] for row in receipts})==4


@pytest.mark.parametrize('control',['stop','steer'])
def test_stale_turn_cannot_control_new_execution_in_same_session(tree,monkeypatch,control):
    turn=_execution(tree)
    child_hosts._update_child_execution(tree,turn['session_id'],{'turn_id':'WT-new-execution'})
    terminated=[]
    monkeypatch.setattr(child_hosts,'_terminate_owned_process',lambda identity:terminated.append(identity))
    with pytest.raises(ValueError,match='another turn'):
        if control=='stop':turn_control.interrupt_turn(tree,{'turn_id':turn['id'],'project':'book'})
        else:turn_control._queue_child_steering(tree,turn,{'turn_id':turn['id'],'text':'stale'})
    assert not terminated
    assert not child_hosts._host_path(tree,turn['session_id']).with_suffix('.cancel.json').exists()
    assert not list(child_hosts._steer_mailbox(tree,turn['session_id']).glob('*.request.json'))


@pytest.mark.parametrize('finish',['terminal','crash'])
def test_pending_and_inflight_controls_remain_distinct_after_terminal_or_crash(tree,monkeypatch,finish):
    turn=_execution(tree)
    first=_admit(tree,turn,'first potentially sent')
    second=_admit(tree,turn,'second still queued')
    ack=first[0].with_name(first[0].name.replace('.request.json','.ack.json'))
    child_hosts._write_host(ack,{**first[1],'state':'DELIVERING'})
    if finish=='terminal':child_hosts._finish_child_execution(tree,turn['session_id'],turn['id'],'interrupted')
    else:child_hosts._update_child_execution(tree,turn['session_id'],{'host':{'pid':999999999,'created_at':-1}})
    observed=session_reads.child_execution(tree,turn['session_id'],controls=True)
    assert [(row['control_id'],row['state']) for row in observed['controls']]==[
        (first[1]['control_id'],'UNCONFIRMED'),(second[1]['control_id'],'FAILED')]
    calls=[]
    monkeypatch.setattr(turn_control,'steer_turn',lambda *args:calls.append(args))
    turn_control._deliver_child_steering(tree,turn['session_id'],turn['id'])
    assert not calls
    assert session_reads._records(tree)['turns'][turn['id']]['session_id']==turn['session_id'], (session_reads._records(tree)['turns'][turn['id']], turn)
    assert _items(tree,turn,item_id=first[1]['control_id'])[0]['state']=='UNCONFIRMED'
    monkeypatch.setattr(owner,'_root',lambda:tree)
    code,_,body=owner.handle('/authoring/session-turn',{'project':'book','id':turn['id'],
          'view':'controls','item_id':second[1]['control_id']},'GET',b'')
    assert code==200 and json.loads(body)['items'][0]['state']=='FAILED'
    state=session_reads.session_state(tree,turn['session_id'],view='summary')
    assert state['execution']['controls_total']==2
    summary=state['turns'][0]
    assert summary['parent_turn_id']==turn['parent_turn_id'] and summary['dispatch_id']=='WORK-controls'


def test_late_native_ack_after_terminal_is_unconfirmed_and_never_replayed(tree,monkeypatch):
    turn=_execution(tree)
    request,receipt=_admit(tree,turn,'inflight')
    entered=threading.Event();release=threading.Event();calls=[]
    def deliver(*args):
        calls.append(args);entered.set();assert release.wait(5);return {'native_steered':True}
    monkeypatch.setattr(turn_control,'steer_turn',deliver)
    worker=threading.Thread(target=turn_control._deliver_child_steering,args=(tree,turn['session_id'],turn['id']))
    worker.start();assert entered.wait(5)
    child_hosts._finish_child_execution(tree,turn['session_id'],turn['id'],'completed')
    release.set();worker.join(timeout=5);assert not worker.is_alive()
    assert _items(tree,turn,item_id=receipt['control_id'])[0]['state']=='UNCONFIRMED'
    turn_control._deliver_child_steering(tree,turn['session_id'],turn['id'])
    assert len(calls)==1


def test_concurrent_delivery_does_not_skip_an_inflight_first_command(tree,monkeypatch):
    turn=_execution(tree)
    _admit(tree,turn,'first');_admit(tree,turn,'second')
    entered=threading.Event();release=threading.Event();texts=[]
    def deliver(root,payload):
        texts.append(payload['text'])
        if payload['text']=='first':entered.set();assert release.wait(5)
        return {'ok':True}
    monkeypatch.setattr(turn_control,'steer_turn',deliver)
    worker=threading.Thread(target=turn_control._deliver_child_steering,args=(tree,turn['session_id'],turn['id']))
    worker.start();assert entered.wait(5)
    turn_control._deliver_child_steering(tree,turn['session_id'],turn['id'])
    assert texts==['first']
    release.set();worker.join(timeout=5)
    assert texts==['first','second'] and not worker.is_alive()


def test_queued_control_is_not_delivered_after_host_crash(tree,monkeypatch):
    turn=_execution(tree)
    _,receipt=_admit(tree,turn,'still queued')
    child_hosts._update_child_execution(tree,turn['session_id'],{'host':{'pid':999999999,'created_at':-1}})
    calls=[]
    monkeypatch.setattr(turn_control,'steer_turn',lambda *args:calls.append(args))
    turn_control._deliver_child_steering(tree,turn['session_id'],turn['id'])
    assert not calls and _items(tree,turn,item_id=receipt['control_id'])[0]['state']=='FAILED'


def test_new_host_cannot_replay_an_admission_owned_by_old_host(tree,monkeypatch):
    turn=_execution(tree)
    _,receipt=_admit(tree,turn,'old host command')
    process=subprocess.Popen([sys.executable,'-S','-c','import time;time.sleep(20)'])
    try:
        child_hosts._update_child_execution(tree,turn['session_id'],{'host':child_hosts._process_identity(process.pid)})
        calls=[]
        monkeypatch.setattr(turn_control,'steer_turn',lambda *args:calls.append(args))
        turn_control._deliver_child_steering(tree,turn['session_id'],turn['id'])
        assert not calls and _items(tree,turn,item_id=receipt['control_id'])[0]['state']=='FAILED'
    finally:
        process.terminate();process.wait(timeout=5)


def test_provider_birth_before_assignment_demonstrates_unobserved_crash_window(tree,monkeypatch):
    """Coverage limit: an OS process can exist before WritingTurn exposes its identity."""
    from test_writing_dispatch_lifecycle import STUB_RUNTIME, _wait
    turn=_execution(tree)
    runtime=tree/'birth-window-runtime';runtime.mkdir()
    gated=STUB_RUNTIME.replace('import subprocess, threading, json\n','import subprocess, threading, json, time\n')
    original="self.process=subprocess.Popen([sys.executable,'-S','-c','import time; time.sleep(60)'],start_new_session=True)"
    replacement="""created=subprocess.Popen([sys.executable,'-S','-c','import time; time.sleep(60)'],start_new_session=True)
        (self.root/'unobserved-provider.json').write_text(json.dumps(a._process_identity(created.pid)))
        while True:time.sleep(.05)"""
    assert original in gated
    (runtime/'sitecustomize.py').write_text(gated.replace(original,replacement))
    source=Path(owner.__file__).resolve().parents[2]
    monkeypatch.setenv('PYTHONPATH',os.pathsep.join(map(str,[runtime,source,Path(__file__).resolve().parent])))
    monkeypatch.setenv('LAPLACE_GUARD_TESTS',str(Path(__file__).resolve().parent));monkeypatch.setenv('LAPLACE_GUARD_LOG',str(tree/'guard-denials.jsonl'))
    monkeypatch.setattr(turn_jobs, '_CHILD_HOST',False)
    started=turn_admission.start_turn(tree,{'project':'book','session_id':turn['session_id'],'mode':'work','text':'inert birth window'},
                             dispatch={'dispatch_id':'WORK-window','parent_turn_id':turn['parent_turn_id']})
    provider={};host={}
    try:
        proof=tree/'unobserved-provider.json';_wait(lambda:proof.exists())
        provider=json.loads(proof.read_text())
        execution=session_reads.child_execution(tree,turn['session_id']);host=execution['host']
        assert not execution.get('provider_process') and child_hosts._process_matches(provider)
        import psutil
        assert child_hosts._process_matches(host)
        psutil.Process(host['pid']).kill()
        _wait(lambda:not child_hosts._process_matches(host))
        observed=session_reads.child_execution(tree,turn['session_id'])
        # This asserts the demonstrated gap; it does not award orphan-recovery acceptance.
        assert observed['state']=='FAILED' and child_hosts._process_matches(provider)
        assert not child_hosts.active_child_hosts(tree)
    finally:
        child_hosts._terminate_owned_process(provider)
        child_hosts._terminate_owned_process(host)


def test_control_ordinal_is_not_reused_after_partial_admission_write_failure(tree,monkeypatch):
    turn=_execution(tree)
    write=child_hosts._write_host
    def failed_ack(path,value):
        if path.name.endswith('.ack.json'):raise OSError('fixture ack admission failed')
        return write(path,value)
    monkeypatch.setattr(child_hosts,'_write_host',failed_ack)
    with pytest.raises(OSError,match='ack admission failed'):_admit(tree,turn,'first incomplete admission')
    monkeypatch.setattr(child_hosts,'_write_host',write)
    _,second=_admit(tree,turn,'second admitted')
    assert second['sequence']==2
    texts=[]
    monkeypatch.setattr(turn_control,'steer_turn',lambda root,payload:texts.append(payload['text']) or {})
    turn_control._deliver_child_steering(tree,turn['session_id'],turn['id'])
    assert texts==['second admitted']
    assert [row['state'] for row in _items(tree,turn)]==['UNCONFIRMED','DELIVERED']


def test_health_does_not_hydrate_finished_control_history(tree,monkeypatch):
    directory=child_hosts._host_directory(tree)
    for index in range(30):
        session='WS-cost-'+str(index)
        child_hosts._write_host(child_hosts._host_path(tree,session),{'state':'FINISHED','session_id':session,
                          'turn_id':'WT-cost-'+str(index),'control_sequence':12})
        for control in range(12):
            name=f'{control+1:020d}-'+f'{control:032x}'
            box=child_hosts._steer_mailbox(tree,session)
            child_hosts._write_host(box/(name+'.request.json'),{'payload':{'text':'historical body'}})
            child_hosts._write_host(box/(name+'.ack.json'),{'state':'DELIVERED','turn_id':'WT-cost-'+str(index)})
    read=child_hosts._read_host;control_reads=[];host_reads=[]
    def observed(path):
        (control_reads if path.parent.name.endswith('.controls') else host_reads).append(path)
        return read(path)
    monkeypatch.setattr(child_hosts,'_read_host',observed)
    for _ in range(3):assert child_hosts.active_child_hosts(tree)==[]
    assert control_reads==[] and len(host_reads)<=90


def test_unchanged_governor_does_not_rescan_delivered_history(tree,monkeypatch):
    turn=_execution(tree)
    child_hosts._update_child_execution(tree,turn['session_id'],{'control_sequence':100,'control_completed_sequence':100})
    box=child_hosts._steer_mailbox(tree,turn['session_id'])
    for control in range(100):
        name=f'{control+1:020d}-'+f'{control:032x}'
        child_hosts._write_host(box/(name+'.request.json'),{'payload':{'text':'delivered historical body'}})
        child_hosts._write_host(box/(name+'.ack.json'),{'state':'DELIVERED','turn_id':turn['id']})
    read=child_hosts._read_host;control_reads=[]
    def observed(path):
        if path.parent==box:control_reads.append(path)
        return read(path)
    monkeypatch.setattr(child_hosts,'_read_host',observed)
    for _ in range(400):turn_control._deliver_child_steering(tree,turn['session_id'],turn['id'])
    assert control_reads==[]


def test_local_followup_stop_ignores_old_finished_child_manifest(tree,monkeypatch):
    from test_writing_dispatch import _settle
    turn=_execution(tree)
    child_hosts._update_child_execution(tree,turn['session_id'],{'dependency_state':'BLOCKED','dependencies':['old'],
        'reason':'old failure','provider_phase':'old provider','control_sequence':7,'control_completed_sequence':7})
    child_hosts._finish_child_execution(tree,turn['session_id'],turn['id'],'completed')
    gate=threading.Event();interrupts=[]
    class Local:
        def __init__(self,*args,**kwargs):self.inference_started=False;self.native_id=None
        def run(self,prompt):assert gate.wait(5);return {'status':'interrupted','text':'local stopped'}
        def interrupt(self):interrupts.append('exact local');gate.set();return {}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Local)
    started=turn_admission.start_turn(tree,{'project':'book','session_id':turn['session_id'],'mode':'work','text':'explicit local follow-up'})
    _wait=lambda:turn_jobs._JOBS[started['turn_id']].get('provider') is not None
    for _ in range(100):
        if _wait():break
        threading.Event().wait(.01)
    assert _wait()
    fresh=session_reads.child_execution(tree,turn['session_id'])
    assert fresh['state']=='RUNNING' and fresh['turn_id']==started['turn_id']
    assert not {'result_status','finished_at','dependency_state','dependencies','reason','provider_phase'} & fresh.keys()
    assert fresh['control_sequence']==fresh['control_completed_sequence']==7
    child_hosts._finish_child_execution(tree,turn['session_id'],turn['id'],'failed')
    child_hosts._update_child_execution(tree,turn['session_id'],{'reason':'late old update'},expected_turn_id=turn['id'])
    assert session_reads.child_execution(tree,turn['session_id'])['turn_id']==started['turn_id']
    result=turn_control.interrupt_turn(tree,{'turn_id':started['turn_id'],'project':'book'})
    assert result['turn_ids']==[started['turn_id']] and interrupts==['exact local']
    _settle(tree,[started],timeout=5)
    assert session_reads.child_execution(tree,turn['session_id'])['turn_id']==started['turn_id']


@pytest.mark.parametrize('provider_name',['codex','claude'])
def test_trusted_capability_observations_are_scoped_changed_only_and_release_dispatch_lock(tree,monkeypatch,provider_name):
    from laplace.work import project_work
    turn=_execution(tree);lock=project_work.dispatch_lock(tree)
    class Condition:
        def __enter__(self):assert not lock.is_locked
        def __exit__(self,*args):pass
        def notify_all(self):pass
    job={'id':turn['id'],'session_id':turn['session_id'],'project':'book','condition':Condition(),
         'events':[{'type':'progress','seq':1}],'done':False,'observation_lock':threading.Lock()}
    WritingTurn = REAL_TURN   # the real provider's pure capability table; never constructed (object.__new__)
    # Exercise the real capability owner without creating a provider process.
    provider=object.__new__(WritingTurn)
    provider.provider=provider_name;provider.conn=None;provider.turn_id=None
    provider.project='book';provider.inference_started=False
    monkeypatch.setattr(child_hosts,'_child_control_rows',lambda *a,**k:pytest.fail('capability stream must not hydrate controls'))
    for _ in range(20):child_hosts._publish_execution_observation(tree,job,provider)
    assert len(job['events'])==2 and not job['events'][-1]['capabilities']['can_steer']
    provider.conn=object();provider.turn_id='native-turn';provider.inference_started=True
    for _ in range(20):child_hosts._publish_execution_observation(tree,job,provider)
    assert len(job['events'])==(3 if provider_name=='codex' else 2)
    event=job['events'][-1]
    assert event['project']=='book' and event['session_id']==turn['session_id'] and event['turn_id']==turn['id']
    assert event['seq']==len(job['events']) and event['capabilities']['can_steer']==(provider_name=='codex')
    child_hosts._begin_child_execution(tree,turn['session_id'],{'session_id':turn['session_id'],'project':'book',
        'turn_id':'WT-newer','state':'RUNNING','host':child_hosts._process_identity()})
    provider.conn=None;provider.turn_id=None;child_hosts._publish_execution_observation(tree,job,provider)
    assert len(job['events'])==(3 if provider_name=='codex' else 2)


def test_fresh_execution_preserves_only_proven_launcher_and_mailbox_coordinates(tree,monkeypatch):
    turn=_execution(tree);sid=turn['session_id']
    child_hosts._write_host(child_hosts._host_path(tree,sid),{'state':'STARTING','session_id':sid,'project':'book',
        'dispatch_id':'WORK-admitted','parent_turn_id':'WT-parent','packet':'selected-worker',
        'launcher':child_hosts._process_identity(),'provider':'claude','control_sequence':9,'control_completed_sequence':8,
        'finished_at':3,'result_status':'completed','provider_phase':'old','dependency_state':'BLOCKED'})
    admission={'state':'RUNNING','session_id':sid,'project':'book','turn_id':'WT-fresh','dispatch_id':'WORK-admitted',
               'parent_turn_id':'WT-parent','host':child_hosts._process_identity()}
    child_hosts._begin_child_execution(tree,sid,admission)
    observed=child_hosts._child_execution_record(tree,sid)
    assert observed=={**admission,'launcher':child_hosts._process_identity(),'provider':'claude','packet':'selected-worker',
                      'control_sequence':9,'control_completed_sequence':8}
    child_hosts._finish_child_execution(tree,sid,'WT-fresh','completed')
    finished=child_hosts._host_path(tree,sid).parent/'finished'/child_hosts._host_path(tree,sid).name;retained=finished.read_bytes()
    child_hosts._begin_child_execution(tree,sid,{**admission,'turn_id':'WT-after-crash','dispatch_id':None,'parent_turn_id':None})
    assert finished.read_bytes()==retained
    assert 'launcher' not in child_hosts._child_execution_record(tree,sid)


def test_older_paused_capability_sample_cannot_publish_after_newer_ready_observation(tree,monkeypatch):
    WritingTurn = REAL_TURN   # the real provider's pure capability table; never constructed (object.__new__)
    turn=_execution(tree)
    job={'id':turn['id'],'session_id':turn['session_id'],'project':'book','condition':threading.Condition(),
         'events':[],'done':False,'observation_lock':threading.Lock()}
    provider=object.__new__(WritingTurn)
    provider.provider='codex';provider.conn=None;provider.turn_id=None;provider.project='book';provider.inference_started=False
    sampled=threading.Event();release=threading.Event();attempted=threading.Event();calls=[]
    real=child_hosts._provider_controls
    def pause(value):
        result=real(value);calls.append(result['can_steer'])
        if len(calls)==1:
            sampled.set();assert release.wait(5)
        return result
    monkeypatch.setattr(child_hosts,'_provider_controls',pause)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        old=pool.submit(child_hosts._publish_execution_observation,tree,job,provider);assert sampled.wait(5)
        provider.conn=object();provider.turn_id='native-ready'
        def newer():attempted.set();child_hosts._publish_execution_observation(tree,job,provider)
        latest=pool.submit(newer);assert attempted.wait(5)
        assert calls==[False], 'new sample must wait for the complete old publication'
        release.set();old.result(timeout=5);latest.result(timeout=5)
    assert [event['capabilities']['can_steer'] for event in job['events']]==[False,True]
    assert child_hosts._child_execution_record(tree,turn['session_id'])['control_capabilities']['can_steer'] is True


def test_orphaned_provider_blocks_new_session_turn(tree,monkeypatch):
    turn=_execution(tree)
    process=subprocess.Popen([sys.executable,'-S','-c','import time;time.sleep(20)'])
    try:
        child_hosts._update_child_execution(tree,turn['session_id'],{'host':{'pid':999999999,'created_at':-1},
              'provider_process':child_hosts._process_identity(process.pid)})
        assert session_reads.child_execution(tree,turn['session_id'])['state']=='ORPHANED'
        with pytest.raises(ValueError,match='session is working'):
            turn_admission.start_turn(tree,{'project':'book','session_id':turn['session_id'],'mode':'work','text':'cannot bypass orphan'})
    finally:
        process.terminate();process.wait(timeout=5)


def _sleeper():
    return subprocess.Popen([sys.executable,'-S','-c','import time;time.sleep(30)'],start_new_session=True)


def test_strict_provider_registrar_still_refuses_another_process_host(tree):
    """The provider spawn guard is unchanged: only the recorded host process may register a provider."""
    turn=_execution(tree);host=_sleeper();provider=_sleeper()
    try:
        child_hosts._update_child_execution(tree,turn['session_id'],{'host':child_hosts._process_identity(host.pid),
            'provider_process':None,'provider_processes':[],'provider_phase':'inference','provider_inference_started':True})
        before=child_hosts._child_execution_record(tree,turn['session_id'])
        with pytest.raises(child_hosts.ProviderError,match='no longer belongs'):
            child_hosts._register_child_process(tree,turn['session_id'],turn['id'],provider,'provider')
        assert child_hosts._child_execution_record(tree,turn['session_id'])==before
    finally:
        for process in (host,provider):process.kill();process.wait(timeout=5)


def test_auxiliary_process_keeps_provider_facts_and_joins_stop_and_orphan_observation(tree,monkeypatch):
    """A trusted auxiliary (development check) registers from ANOTHER process of the turn by generation; provider facts
    stay; Stop and the ORPHANED observation include it; an unregistered process is untouched; a stale generation cannot
    register into, or be reported by, a newer turn of the same session."""
    turn=_execution(tree);sid=turn['session_id']
    host,aux,unrelated,provider=_sleeper(),_sleeper(),_sleeper(),_sleeper()
    try:
        provider_identity=child_hosts._process_identity(provider.pid)
        child_hosts._update_child_execution(tree,sid,{'host':child_hosts._process_identity(host.pid),'provider_process':provider_identity,
            'provider_processes':[provider_identity],'provider_phase':'inference','provider_inference_started':True})
        generation=child_hosts.auxiliary_generation(tree,sid,turn['id'])
        assert generation['host']['pid']==host.pid!=os.getpid()
        entry=child_hosts._register_auxiliary_process(tree,generation,aux,'development-check')
        row=child_hosts._child_execution_record(tree,sid)
        assert entry['pid']==aux.pid and entry['registrant']['pid']==os.getpid()!=host.pid and entry['phase']=='development-check'
        assert (row['provider_process'],row['provider_processes'],row['provider_phase'],row['provider_inference_started'])==(
            provider_identity,[provider_identity],'inference',True)
        observed=session_reads.child_execution(tree,sid)
        assert observed['active_auxiliary_processes']==[entry] and observed['active_provider_processes']==[provider_identity]
        # the host dies while the auxiliary lives: ORPHANED, not FAILED, and its identity is reported
        host.kill();host.wait(timeout=5);provider.kill();provider.wait(timeout=5)
        orphan=session_reads.child_execution(tree,sid)
        assert orphan['state']=='ORPHANED' and orphan['active_auxiliary_processes']==[entry] and orphan['active_provider_processes']==[]
        assert child_hosts.auxiliary_problem(tree,generation)=='the host process exited'
        with pytest.raises(child_hosts.ProviderError,match='host process exited'):
            child_hosts._register_auxiliary_process(tree,generation,unrelated,'development-check')
        # the exact Stop terminates the registered auxiliary by birth identity; the unregistered process lives
        turn_control.interrupt_turn(tree,{'turn_id':turn['id'],'project':'book'})
        aux.wait(timeout=5)
        assert not child_hosts._process_matches(entry) and unrelated.poll() is None
    finally:
        for process in (host,aux,unrelated,provider):
            if process.poll() is None:process.kill()
            process.wait(timeout=5)


def test_stale_auxiliary_generation_cannot_register_into_newer_turn(tree):
    turn=_execution(tree);sid=turn['session_id']
    generation=child_hosts.auxiliary_generation(tree,sid,turn['id'])
    assert generation is not None
    child_hosts._begin_child_execution(tree,sid,{'session_id':sid,'project':'book','turn_id':'WT-newer','state':'RUNNING',
        'host':child_hosts._process_identity(),'provider_processes':[]})
    newer=child_hosts._child_execution_record(tree,sid);stale=_sleeper()
    try:
        assert child_hosts.auxiliary_problem(tree,generation)=='a newer turn owns this session'
        with pytest.raises(child_hosts.ProviderError,match='newer turn'):
            child_hosts._register_auxiliary_process(tree,generation,stale,'development-check')
        assert child_hosts._child_execution_record(tree,sid)==newer and 'auxiliary_processes' not in newer
        assert child_hosts.auxiliary_generation(tree,sid,turn['id']) is None
        # a recorded host whose pid is alive but whose birth time differs is not this generation (pid reuse)
        child_hosts._update_child_execution(tree,sid,{'host':{'pid':os.getpid(),'created_at':-1.0}})
        assert child_hosts.auxiliary_generation(tree,sid,'WT-newer') is None
    finally:
        stale.kill();stale.wait(timeout=5)


@pytest.mark.parametrize('publish_suffix', ['.request.json', '.ack.json'])
def test_governor_cannot_skip_admission_during_publication(tree, monkeypatch, publish_suffix):
    from laplace.work import project_work
    turn = _execution(tree)
    paused, release, delivery_started = threading.Event(), threading.Event(), threading.Event()
    write = child_hosts._write_host
    lock = project_work.dispatch_lock
    errors, texts = [], []
    def publish(path, value):
        if threading.current_thread().name == 'admission' and path.name.endswith(publish_suffix):
            paused.set()
            assert release.wait(5)
        return write(path, value)
    def admit():
        try: _admit(tree, turn, 'retained correction')
        except Exception as exc: errors.append(exc)
    def deliver():
        try: turn_control._deliver_child_steering(tree, turn['session_id'], turn['id'])
        except Exception as exc: errors.append(exc)
    def observed_lock(root):
        if threading.current_thread().name == 'delivery':delivery_started.set()
        return lock(root)
    monkeypatch.setattr(child_hosts,'_write_host', publish)
    monkeypatch.setattr(project_work, 'dispatch_lock', observed_lock)
    monkeypatch.setattr(turn_control,'steer_turn', lambda root, payload: texts.append(payload['text']) or {})
    admission = threading.Thread(target=admit, name='admission')
    admission.start()
    assert paused.wait(5)
    delivery = threading.Thread(target=deliver, name='delivery')
    delivery.start()
    try:
        assert delivery_started.wait(5)
        # Partial admission is never a completed delivery, including while the
        # request exists but its acknowledgement has not yet been published.
        assert not texts
        row = child_hosts._child_execution_record(tree, turn['session_id'])
        assert not row.get('control_completed_sequence')
    finally:
        release.set()
        admission.join(5)
        delivery.join(5)
    assert not admission.is_alive() and not delivery.is_alive() and not errors
    turn_control._deliver_child_steering(tree, turn['session_id'], turn['id'])
    assert texts == ['retained correction']
    assert [row['state'] for row in _items(tree, turn)] == ['DELIVERED']


@pytest.mark.parametrize('inference', [True, False])
def test_stop_after_recovery_settles_a_turn_whose_host_exited_and_the_native_guard_stays_truthful(tree, inference):
    """Live freeze recovery 2026-10-20: after the frozen service is gone, its running author turn has no live job, its
    execution reads FAILED (recorded host exited) and it saved no terminal reply, so Stop used to refuse and the next
    turn dropped the native conversation. Stop now settles it through the turn's own reply producer: no model text,
    the stage the execution record proved, the recovery basis; the existing native_continuation guard then keeps the
    native id only for a turn that reached inference. A second Stop has nothing to settle."""
    from laplace.writing import turn_admission
    records_fold._CACHE.pop(str(tree / records_fold._STORE), None)
    session = turn_admission.new_session(tree, 'book', 'codex', '', '')
    turn = {'record': 'writing-turn', 'id': 'WT-exited-host', 'project': 'book', 'session_id': session['id'],
            'provider_settings': {'provider': 'codex'}, 'text': 'theory synthesis', 'mode': 'work'}
    writing_records.bank(tree, turn)
    child_hosts._update_child_execution(tree, session['id'], {'session_id': session['id'], 'project': 'book', 'state': 'RUNNING',
        'turn_id': turn['id'], 'host': {'pid': 999999999, 'created_at': -1}, 'provider_processes': [],
        'provider_inference_started': inference})
    assert session_reads.child_execution(tree, session['id'])['state'] == 'FAILED'
    result = turn_control.interrupt_turn(tree, {'turn_id': turn['id'], 'project': 'book'})
    expected = ('interrupted', 'inference') if inference else ('failed', 'pre-inference')
    assert result['turn_ids'] == [turn['id']] and (result['settled']['status'], result['settled']['provider_stage']) == expected
    saved = session_reads._records(tree)['turns'][turn['id']]
    reply = saved['reply']
    assert (reply['status'], reply['provider_stage'], reply['text']) == (*expected, '')
    assert reply['recovery']['basis'] == 'host-exited-without-terminal-reply' and reply['recovery']['provider_inference_started'] is inference
    brief = {'native_registration_signature': 'sig', 'tool_contract_digest': 'kernel', 'shared_rules_revision': 'rules', 'capability_guidance_revision': 'guidance'}
    previous = {**saved, 'orientation': {key: brief[key] for key in ('tool_contract_digest', 'shared_rules_revision', 'capability_guidance_revision')}}
    continued, migration, _ = turn_admission.native_continuation(
        {**session, 'native_id': '01a15901-c5a8-7781-9cc6-9cf1de1ea37d', 'native_registration_signature': 'sig'}, previous, brief)
    if inference:
        assert migration is None and continued['native_id'] == '01a15901-c5a8-7781-9cc6-9cf1de1ea37d'
    else:
        assert migration['reason'].startswith('previous turn ended before inference') and continued['native_id'] is None
    assert session_reads.child_execution(tree, session['id']).get('state') not in {'STARTING', 'WAITING', 'RUNNING'}
    with pytest.raises(ValueError, match='no active provider turn'):
        turn_control.interrupt_turn(tree, {'turn_id': turn['id'], 'project': 'book'})


@pytest.mark.parametrize('race', ['second-stop', 'late-terminal-reply', 'changed-execution'])
def test_recovery_settlement_publishes_at_most_one_terminal_reply_under_competing_stops(tree, monkeypatch, race):
    """LF-R2: the first Stop pauses at the point where it would publish; meanwhile a second Stop runs, or a terminal
    reply lands, or the execution record changes. Exactly one terminal reply (and one delivery settlement) results
    from two Stops and the second refuses; a late reply or a changed execution makes the recovery publish nothing."""
    from laplace.writing import turn_admission, turn_execution
    from laplace.work import work_delivery
    records_fold._CACHE.pop(str(tree / records_fold._STORE), None)
    session = turn_admission.new_session(tree, 'book', 'codex', '', '')
    turn = {'record': 'writing-turn', 'id': 'WT-raced-host', 'project': 'book', 'session_id': session['id'],
            'provider_settings': {'provider': 'codex'}, 'text': 'theory synthesis', 'mode': 'work'}
    writing_records.bank(tree, turn)
    child_hosts._update_child_execution(tree, session['id'], {'session_id': session['id'], 'project': 'book', 'state': 'RUNNING',
        'turn_id': turn['id'], 'host': {'pid': 999999999, 'created_at': -1}, 'provider_processes': [], 'provider_inference_started': True})
    settlements, outcomes = [], {}
    real_settle_turn = work_delivery.settle_turn
    monkeypatch.setattr(work_delivery, 'settle_turn', lambda *a, **k: settlements.append(a[3]) or real_settle_turn(*a, **k))
    real = turn_execution.settle_exited_host
    paused, second_done = threading.Event(), threading.Event()

    def at_publication(*args, **kwargs):
        if threading.current_thread().name == 'first-stop':
            paused.set()
            if race == 'second-stop':
                second_done.wait(2)   # the second Stop either finishes (no boundary) or waits on the per-turn owner lock
            elif race == 'late-terminal-reply':
                writing_records.bank(tree, {'record': 'writing-reply', 'id': 'WR-late-terminal', 'turn_id': turn['id'], 'session_id': session['id'],
                                   'project': 'book', 'status': 'completed', 'text': 'a late terminal reply'})
            else:
                child_hosts._update_child_execution(tree, session['id'], {'host': {'pid': 999999998, 'created_at': -2}}, expected_turn_id=turn['id'])
        return real(*args, **kwargs)
    monkeypatch.setattr(turn_execution, 'settle_exited_host', at_publication)

    def stop(name):
        try:
            outcomes[name] = turn_control.interrupt_turn(tree, {'turn_id': turn['id'], 'project': 'book'})
        except ValueError as exc:
            outcomes[name] = 'refused: ' + str(exc)
        finally:
            if name == 'second-stop':
                second_done.set()
    first = threading.Thread(target=stop, args=('first-stop',), name='first-stop')
    first.start()
    assert paused.wait(10)
    if race == 'second-stop':
        second = threading.Thread(target=stop, args=('second-stop',), name='second-stop')
        second.start(); second.join(20)
        assert not second.is_alive()
    first.join(20)
    assert not first.is_alive()
    replies = [json.loads(line) for line in (tree / records_fold._STORE).read_text().splitlines()
               if '"writing-reply"' in line and turn['id'] in line]
    replies = [row for row in replies if row.get('record') == 'writing-reply' and row.get('turn_id') == turn['id']]
    if race == 'second-stop':
        assert len(replies) == 1 and replies[0]['status'] == 'interrupted' and replies[0]['text'] == '' and settlements == [turn['id']], (replies, settlements)
        assert sorted(isinstance(value, dict) for value in outcomes.values()) == [False, True], outcomes
        assert next(value for value in outcomes.values() if isinstance(value, str)).startswith('refused: There is no active provider turn')
    elif race == 'late-terminal-reply':
        assert [row['id'] for row in replies] == ['WR-late-terminal'] and settlements == [], (replies, settlements)
        assert outcomes['first-stop'].startswith('refused: ')
    else:
        assert replies == [] and settlements == [] and outcomes['first-stop'].startswith('refused: '), (replies, outcomes)
