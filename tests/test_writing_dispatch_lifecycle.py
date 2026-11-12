"""Bounded execution-owner tests, including real detached host processes, no inference."""
from __future__ import annotations
from work_read_helpers import guarded_transition, standing_payload
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest
from laplace.web import authoring as authoring_surface
from laplace.work import project_work
from laplace.native import tools as writing_tools
from laplace.projects import artifacts as writing_artifacts
from laplace.writing import child_hosts
from laplace.writing import turn_admission
from laplace.writing import session_reads
from laplace.writing import dispatch_execution
from laplace.writing import turn_jobs
from laplace.writing import records as writing_records
from laplace.writing.records import _fold as records_fold
from laplace.core import checkout
from test_writing_dispatch import tree, CATALOGUE, _plan, _parent_turn, _settle, _return_document, _StubTurn


def _planned(root, plan=None):
    _, parent = _parent_turn(root)
    result = writing_tools.execute(root, 'book', 'work', 'dispatch_plan',
        {'title': 'controlled work', 'goal': 'bounded work', 'path': 'dispatch/plan.json',
         'plan': plan or _plan(root)}, turn_id=parent)
    return parent, result['dispatch_id']


def _status(root, ident):
    return project_work.dispatch_view(project_work._tasks('book',root)[ident], 'book', root)


def _wait(predicate, seconds=15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        time.sleep(.05)
    raise AssertionError('bounded wait did not observe completion')


def test_admission_precedes_effects_and_concurrent_retry_reuses_children(tree, monkeypatch):
    root=tree
    parent, ident=_planned(root)
    original=turn_admission.new_session
    admitted=[]
    def opening(*args, **kw):
        if kw.get('dispatch_id'):
            row=project_work._tasks('book',root)[ident]
            admitted.append(row['dispatch_admitted'] and row['status']=='in-progress')
        return original(*args, **kw)
    monkeypatch.setattr(turn_admission, 'new_session',opening)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(dispatch_execution.launch_dispatch,root,'book',parent,{'id':ident}) for _ in range(2)]
        results=[future.result() for future in futures]
    assert admitted==[True]*3
    children=[row for row in session_reads._records(root)['turns'].values() if row.get('dispatch_id')==ident]
    assert len(children)==3
    assert sum(bool(result.get('reused')) for result in results)==1
    _settle(root,[{'turn_id':row['id']} for row in children])
    assert child_hosts.active_child_hosts(root)==[]
    assert all(session_reads.child_execution(root,row['session_id'])['state'] in {'FINISHED','BLOCKED'} for row in children)


@pytest.mark.parametrize('mutation', ['model','effort','collision','alias','existing','deadline','other-dispatch'])
def test_all_refusals_precede_session_and_provider_effects(tree, mutation):
    root=tree
    parent, ident=_planned(root)
    path=writing_artifacts.resolve_path(root,'book','dispatch/plan.json')
    plan=json.loads(path.read_text())
    if mutation in {'model','effort'}:plan['packets'][-1][mutation]='invalid'
    elif mutation=='collision':plan['packets'][-1]['return_path']=plan['packets'][0]['return_path']
    elif mutation=='alias':plan['packets'][-1]['return_path']='dispatch/./worker-a.return.json'
    elif mutation=='deadline':plan['deadline_seconds']=True
    elif mutation=='other-dispatch':
        project_work.task('book',{'title':'other','goal':'other','kind':'dispatch','evidence':[path.relative_to(root).as_posix()]},root)
    else:writing_artifacts.resolve_path(root,'book','dispatch/worker-a.return.json').write_text('existing output')
    path.write_text(json.dumps(plan))
    before=session_reads._records(root)
    with pytest.raises(ValueError):dispatch_execution.launch_dispatch(root,'book',parent,{'id':ident})
    after=session_reads._records(root)
    assert set(after['sessions'])==set(before['sessions'])
    assert set(after['turns'])==set(before['turns'])
    assert project_work._tasks('book',root)[ident]['status']=='open'


def test_partial_launch_failure_is_banked_and_retry_does_not_replay(tree, monkeypatch):
    root=tree
    parent, ident=_planned(root)
    original=turn_admission.start_turn
    starts=[]
    def starting(*args,**kw):
        starts.append(kw)
        if len(starts)==2:raise ValueError('fixture host failed')
        return original(*args,**kw)
    monkeypatch.setattr(turn_admission, 'start_turn',starting)
    with pytest.raises(ValueError,match='fixture host failed'):
        dispatch_execution.launch_dispatch(root,'book',parent,{'id':ident})
    retry=dispatch_execution.launch_dispatch(root,'book',parent,{'id':ident})
    assert retry['reused'] and retry['execution_state']=='FAILED'
    assert len(starts)==2
    assert project_work._tasks('book',root)[ident]['status']=='blocked'


@pytest.mark.parametrize('kind',['missing','malformed','wrong-packet','schema','failed','interrupted'])
def test_unsuccessful_returns_never_read_complete(tree,kind):
    root=tree
    parent,ident=_planned(root)
    started=dispatch_execution.launch_dispatch(root,'book',parent,{'id':ident})
    _settle(root,started['children'])
    worker=next(row for row in started['children'] if row['packet']=='worker-a')
    output=writing_artifacts.resolve_path(root,'book','dispatch/worker-a.return.json')
    if kind!='missing':
        doc=json.loads(_return_document('worker-a','goal','input',hashlib.sha256(b'input').hexdigest(),'output'))
        if kind=='wrong-packet':doc['packet']='worker-b'
        if kind=='schema':doc={'schema_version':'laplace.packet-return/1','status':'COMPLETE'}
        output.write_text('{bad' if kind=='malformed' else json.dumps(doc))
    if kind in {'failed','interrupted'}:
        writing_records.bank(root,{'record':'writing-reply','id':'WR-terminal-'+kind,
            'turn_id':worker['turn_id'],'session_id':worker['session_id'],'project':'book','status':kind,'text':'fixture'})
    row=next(row for row in _status(root,ident)['children'] if row['packet']=='worker-a')
    assert row['state']!='COMPLETE',row


def test_child_cannot_overwrite_peer_return_or_dispatch_plan(tree):
    root=tree
    parent,ident=_planned(root)
    started=dispatch_execution.launch_dispatch(root,'book',parent,{'id':ident})
    _settle(root,started['children'])
    for child in started['children']:
        mode='review' if child['role']=='judge' else 'work'
        for path in ['dispatch/plan.json','dispatch/worker-b.return.json']:
            if path==child['return_path']:continue
            with pytest.raises(ValueError):
                writing_tools.execute(root,'book',mode,'store_artifact',{'path':path,'scope':'project','content':'overwrite'},turn_id=child['turn_id'])


# Only in these owned subprocess fixtures. No production environment flag enables a stub.
STUB_RUNTIME=r'''
# THE CONTAINED CHILD BOOTSTRAP (runtime_guard.BOOTSTRAP): no provider, no network, no canonical state
import os, sys
sys.path.insert(0, os.environ['LAPLACE_GUARD_TESTS'])
import runtime_guard
runtime_guard.install()
runtime_guard.ARMED = True
import subprocess, threading, json
from pathlib import Path
from laplace.writing import provider as wp
from test_writing_dispatch import CATALOGUE
_bound_environment=wp.native_code_environment
def _contained_host_environment(environ=None):
    # The owner binds every detached host to the loaded package. This fixture only prepends its own bootstrap
    # directory (this sitecustomize alone), so each host installs the same guard and stub before any app import.
    env=_bound_environment(environ)
    env['PYTHONPATH']=os.pathsep.join([os.path.dirname(os.path.abspath(__file__)),env['PYTHONPATH']])
    return env
wp.native_code_environment=_contained_host_environment
from laplace.pipeline import schema
CATALOGUE=json.loads(json.dumps(CATALOGUE))
CATALOGUE['providers'].append({'id':'codex','available':True,'models':[
    {'id':model,'resolved_model':model,'supports_effort':True,'efforts':['low','medium','high','xhigh','max','ultra']}
    for model in {schema.role_model(role,'codex')['model'] for role in ['session','worker','judge']}]})
wp.capabilities=lambda *args,**kw: CATALOGUE
wp.provider_catalogue=lambda *args,**kw: CATALOGUE
wp.context_window_advertised=lambda *args,**kw: None
class Stub:
    def __init__(self,root,provider,model,effort,native_id,emit,mode,**kw):
        self.root=Path(root);self.turn_id=kw['logical_turn_id'];self.cancelled=threading.Event()
        self.native_id=native_id;self.inference_started=False;self.process=None
    def run(self,prompt):
        self.process=subprocess.Popen([sys.executable,'-S','-c','import time; time.sleep(60)'],start_new_session=True)
        self.inference_started=True  # fixture native turn phase; no provider inference exists
        if not self.cancelled.wait(20):raise AssertionError('fixture was never controlled')
        self.process.terminate();self.process.wait(timeout=5)
        return {'status':'interrupted','text':'fixture received actual provider control'}
    def control_capabilities(self):
        # This fixture actually implements native steering; the owner no longer
        # infers that capability from the mere presence of a steer method.
        return {'can_interrupt':True,'can_steer':True}
    def steer(self,text):
        path=self.root/'stub-steering';path.mkdir(exist_ok=True)
        (path/self.turn_id).write_text(text)
        return {'native_steered':True}
    def interrupt(self):
        self.cancelled.set()
        path=self.root/'stub-controls';path.mkdir(exist_ok=True)
        (path/self.turn_id).write_text(json.dumps({'host_pid':os.getpid(),'interrupted':True}))
        return {}
wp.WritingTurn=Stub   # THE RUNTIME LOOKUP (turn_execution reads writing_provider.WritingTurn); no facade alias is installed
assert wp.WritingTurn is Stub
'''


@pytest.mark.parametrize('control',['child-stop','parent-stop','cancel','deadline','host-crash','orphan-cancel','steer'])
def test_real_hosts_remain_visible_and_controlled_after_parent_process_exits(tree,monkeypatch,control):
    root=tree
    runtime=root/'fixture-runtime';runtime.mkdir()
    (runtime/'sitecustomize.py').write_text(STUB_RUNTIME)
    source=Path(authoring_surface.__file__).resolve().parents[2]
    tests=Path(__file__).resolve().parent
    env={**os.environ,'PYTHONPATH':os.pathsep.join(map(str,[runtime,source,tests])),
         'LAPLACE_STATE':str(root/'state'),'LAPLACE_TEST_PROCESS':'1',
         'LAPLACE_GUARD_TESTS':str(tests),'LAPLACE_GUARD_LOG':str(root/'guard-denials.jsonl')}
    plan=_plan(root)
    if control=='deadline':plan['deadline_seconds']=8
    if control=='steer':
        from laplace.writing import provider as writing_provider
        from laplace.pipeline import schema
        catalogue=json.loads(json.dumps(CATALOGUE))
        catalogue['providers'].append({'id':'codex','available':True,'models':[
            {'id':model,'resolved_model':model,'supports_effort':True,'efforts':['low','medium','high','xhigh','max','ultra']}
            for model in {schema.role_model(role,'codex')['model'] for role in ['session','worker','judge']}]})
        monkeypatch.setattr(writing_provider,'capabilities',lambda *a,**kw:catalogue)
        for packet in plan['packets']:packet['provider']='codex'
    parent,ident=_planned(root,plan)
    script='''import json,sys
from pathlib import Path
from laplace.writing import dispatch_execution,records
root=Path(sys.argv[1]);ident=sys.argv[2]
started=dispatch_execution.launch_dispatch(root,'book','WT-parent',{'id':ident})
records.bank(root,{'record':'writing-reply','id':'WR-parent-finished','turn_id':'WT-parent','session_id':records.fold_records(root)['turns']['WT-parent']['session_id'],'project':'book','status':'completed','text':'Parent ended after launch'})
print(json.dumps(started))
'''
    result=subprocess.run([sys.executable,'-c',script,str(root),ident],env=env,cwd=root,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr or result.stdout
    started=json.loads(result.stdout)
    assert len(started['children'])==3
    monkeypatch.setattr(checkout, 'repo_root',lambda:root)
    try:
        workers=[row for row in started['children'] if row['role']=='worker']
        judge=next(row for row in started['children'] if row['role']=='judge')
        _wait(lambda:all(session_reads.child_execution(root,row['session_id']).get('provider_process') for row in workers)
              and session_reads.child_execution(root,judge['session_id']).get('state')=='WAITING')
        assert not session_reads.child_execution(root,judge['session_id']).get('provider_process')
        assert _status(root,ident)['children'][-1]['state']=='WAITING'
        assert session_reads._records(root)['turns'][parent]['reply']['status']=='completed'
        assert turn_jobs.active_turn_count()==3
        rows,omitted=turn_jobs.active_work_projection()
        assert {row['turn_id'] for row in rows}=={row['turn_id'] for row in started['children']} and omitted==0
        child=started['children'][0]
        assert session_reads.session_state(root,child['session_id'],view='summary')['active']['id']==child['turn_id']
        code,_,body=authoring_surface.handle('/authoring/health',{},'GET',b'')
        assert code==200 and json.loads(body)['active_turns']==3
        if control=='steer':
            code,_,body=authoring_surface.handle('/authoring/steer',{},'POST',json.dumps(
                {'turn_id':child['turn_id'],'project':'book','text':'Continue from the selected conversation'}).encode())
            assert code==200,body
            delivered=json.loads(body)
            assert delivered['delivery']=='DELIVERED' and delivered['native_steered']
            assert (root/'stub-steering'/child['turn_id']).read_text()=='Continue from the selected conversation'
            assert session_reads.session_state(root,child['session_id'],view='summary')['active']['control']['state']=='DELIVERED'
            guarded_transition('book',{'id':ident,'status':'cancelled'},root)
        elif control=='cancel':
            guarded_transition('book',{'id':ident,'status':'cancelled'},root)
        elif control!='deadline':
            target=child['turn_id'] if control in {'child-stop','host-crash','orphan-cancel'} else parent
            if control in {'host-crash','orphan-cancel'}:
                import psutil
                host=session_reads.child_execution(root,child['session_id'])['host']
                psutil.Process(host['pid']).kill()
                _wait(lambda:session_reads.child_execution(root,child['session_id']).get('state')=='ORPHANED')
                # Read remains passive; crash does not erase activity or replay the child.
                assert _status(root,ident)['children'][0]['state']=='FAILED'
                retry=dispatch_execution.launch_dispatch(root,'book',parent,{'id':ident})
                assert retry['reused'] and len(retry['children'])==3
            if control=='orphan-cancel':
                guarded_transition('book',{'id':ident,'status':'cancelled'},root)
                code,body=200,b'{}'
            else:
                code,_,body=authoring_surface.handle('/authoring/interrupt',{},'POST',json.dumps({'turn_id':target,'project':'book'}).encode())
            if control=='parent-stop':
                assert code==409 and turn_jobs.active_turn_count()==3,body
                guarded_transition('book',{'id':ident,'status':'cancelled'},root)
            else:assert code==200,body
            if control in {'child-stop','host-crash','orphan-cancel'}:
                _wait(lambda:session_reads.child_execution(root,child['session_id']).get('state') not in {'RUNNING','ORPHANED'})
                guarded_transition('book',{'id':ident,'status':'cancelled'},root)
        _wait(lambda:not child_hosts.active_child_hosts(root))
        assert turn_jobs.active_turn_count()==0
        assert all(row['state']!='COMPLETE' for row in _status(root,ident)['children'])
        if control not in {'host-crash','orphan-cancel'}:
            assert len(list((root/'stub-controls').iterdir()))==2  # waiting judge never constructed a provider
            _settle(root,started['children'],timeout=5)
            replies=[session_reads._records(root)['turns'][row['turn_id']]['reply'] for row in started['children']]
            assert all(row['status']=='interrupted' for row in replies)
            if control=='deadline':assert all(row['error']=='deadline exceeded' for row in replies)
    finally:
        for row in started['children']:
            receipt=session_reads.child_execution(root,row['session_id'])
            child_hosts._terminate_owned_process(receipt.get('provider_process') or {})
            child_hosts._terminate_owned_process(receipt.get('host') or {})


def test_control_monitor_reads_history_once_across_many_ticks_and_observes_change(tree,monkeypatch):
    root=tree
    parent,ident=_planned(root)
    path=writing_artifacts.resolve_path(root,'book','dispatch/plan.json')
    guarded_transition('book',{'id':ident,'status':'in-progress'},root,dispatch_receipt={
        'dispatch_plan_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'dispatch_deadline_at':time.time()+60})
    session=session_reads._records(root)['turns'][parent]['session_id']
    tasks=project_work._tasks
    calls=[]
    def read_tasks(*args,**kw):calls.append('ledger');return tasks(*args,**kw)
    monkeypatch.setattr(project_work,'_tasks',read_tasks)
    read_bytes=Path.read_bytes
    plans=[]
    def read_plan(self):
        if self==path:plans.append('plan')
        return read_bytes(self)
    monkeypatch.setattr(Path,'read_bytes',read_plan)
    cache={}
    dispatch={'dispatch_id':ident,'project':'book'}
    for _ in range(400):
        assert dispatch_execution._child_control_reason(root,dispatch,session,cache=cache) is None
    assert calls==['ledger'] and plans==['plan']
    guarded_transition('book',{'id':ident,'status':'cancelled'},root)
    calls.clear()
    assert dispatch_execution._child_control_reason(root,dispatch,session,cache=cache)=='cancelled'
    assert calls==['ledger'] and plans==['plan']


def test_failed_dispatch_cannot_be_marked_done_with_its_plan_as_evidence(tree):
    root=tree
    parent,ident=_planned(root)
    with pytest.raises(ValueError,match='successful typed return'):
        guarded_transition('book',{'id':ident,'status':'done',
            'evidence':project_work._tasks('book',root)[ident]['evidence']},root)


def test_failed_initial_execution_receipt_does_not_leave_an_active_local_job(tree,monkeypatch):
    root=tree
    parent,ident=_planned(root)
    before=set(turn_jobs._JOBS)
    write=child_hosts._write_host
    starting,running,faults=[],[],[]
    def failing(path,value):
        # Only the first admitted child of this real dispatch fails, and only at its initial RUNNING receipt.
        # Its STARTING write and the launch owner's later terminal write still reach the real writer.
        if value.get('dispatch_id')==ident and value.get('state')=='STARTING' and not starting:
            starting.append(value.get('session_id'))
        if value.get('state')=='RUNNING' and starting and value.get('session_id')==starting[0]:
            running.append(value.get('turn_id'))
            if not faults:
                faults.append({key:value.get(key) for key in ('dispatch_id','parent_turn_id','session_id','turn_id')})
                raise OSError('fixture receipt storage failed')
        return write(path,value)
    providers=[];constructed=_StubTurn.__init__
    def constructing(self,*args,**kwargs):
        providers.append(kwargs.get('logical_turn_id'))
        return constructed(self,*args,**kwargs)
    monkeypatch.setattr(_StubTurn,'__init__',constructing)
    monkeypatch.setattr(child_hosts,'_write_host',failing)
    with pytest.raises(OSError,match='receipt storage failed'):
        dispatch_execution.launch_dispatch(root,'book',parent,{'id':ident})
    assert len(starting)==1 and len(running)==1 and len(faults)==1
    fault=faults[0];turn=session_reads._records(root)['turns'][fault['turn_id']]
    assert fault=={'dispatch_id':ident,'parent_turn_id':parent,'session_id':starting[0],'turn_id':turn['id']}
    assert turn['dispatch_id']==ident and turn['session_id']==starting[0]
    assert set(turn_jobs._JOBS)==before and fault['turn_id'] not in turn_jobs._JOBS
    assert providers==[]
    assert child_hosts._child_execution_record(root,starting[0])['state']=='FAILED'
    # An unknown dispatch identity remains refused before any receipt write or local job.
    session=turn_admission.new_session(root,'book','claude','','',model_role='worker')
    with pytest.raises(ValueError,match='exact dispatch'):
        turn_admission.start_turn(root,{'project':'book','session_id':session['id'],
            'mode':'work','text':'fixture'},dispatch={'dispatch_id':'WORK-fixture','parent_turn_id':'WT-parent'})
    assert set(turn_jobs._JOBS)==before and len(running)==1 and providers==[]


def test_validated_work_relationship_survives_session_reload(tree):
    root=tree
    work=project_work.task('book',{'title':'linked work','goal':'relation readback'},root)
    session=turn_admission.new_session(root,'book','claude','','')
    inspected=project_work.read('book',{'view':'detail','id':work['id']},root)['task']
    started=turn_admission.start_turn(root,{'project':'book','session_id':session['id'],
        'mode':'work','text':'Continue the selected work','work_id':work['id'],
        'expected_work_scope_revision':inspected['work_scope_revision'],
        'expected_dependency_revision':inspected['dependency_revision']})
    _settle(root,[started])
    records_fold._CACHE.pop(str(root/records_fold._STORE),None)
    view=session_reads.session_state(root,session['id'],view='summary')
    assert view['turns'][-1]['work_id']==work['id']
    assert turn_jobs._JOBS[started['turn_id']]['work_id']==work['id']
    assert project_work._tasks('book',root)[work['id']]['status']=='open'
