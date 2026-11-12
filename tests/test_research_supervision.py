"""Actual one-shot owners and kernel descendants in small registered projects.

No provider/model/service is launched. Test teardown identifies every owned task
before signalling; the unrelated-process control is intentionally outside scope.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from laplace.research import research_runner as runner
from laplace.web import research_surface as rs
from laplace.research import research_runs
from laplace.research import research_context
from laplace.research import research_context, research_observation, research_runs   # the owners the code paths read (research family R1)

pytestmark = pytest.mark.skipif(runner.capability()['status'] != 'AVAILABLE',
                                reason='Linux subreaper/pidfd ownership capability required')

PRODUCER = '''import argparse,json,os,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args()
args=json.loads(a.args_json)
worker="import os,signal,time,json; from pathlib import Path; from laplace.representation.semantic_cadence import process_start_token; signal.signal(signal.SIGTERM, signal.SIG_IGN); Path('worker.identity').write_text(json.dumps({'pid':os.getpid(),'start_token':process_start_token()})); Path('worker.pid').write_text(str(os.getpid())); time.sleep(60)"
if args.get('kind')=='double':
    worker="import os; pid=os.fork(); os._exit(0) if pid else None; os.setsid(); "+worker
child=subprocess.Popen([sys.executable,'-c',worker],start_new_session=True)
from laplace.representation.semantic_cadence import process_start_token
Path('producer.identity').write_text(json.dumps({'pid':os.getpid(),'start_token':process_start_token()}))
Path('producer.pid').write_text(str(os.getpid()))
while not Path('worker.pid').exists(): time.sleep(.01)
Path(a.result).write_text(json.dumps({'answer':42}))
if args.get('kind')!='exit': time.sleep(60)
'''


def wait_for(read, predicate=lambda x: bool(x), seconds=9):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try: value = read()
        except (OSError, ValueError): value = None
        if predicate(value): return value
        time.sleep(.025)
    raise AssertionError('bounded observation did not settle: ' + repr(value))


@pytest.fixture
def project(tmp_path):
    manuscript = tmp_path / 'fixture' / 'manuscript'
    manuscript.mkdir(parents=True)
    (tmp_path / 'registry_projects.json').write_text(json.dumps({'projects': [{
        'name': 'fixture', 'kind': 'conceptric', 'project_dir': 'fixture',
        'tex_root': 'fixture/manuscript'}]}))
    (manuscript / 'producer.py').write_text(PRODUCER)
    (manuscript / 'research_producers.json').write_text(json.dumps({'producers': [{
        'id': 'bounded', 'executable': 'producer.py', 'modes': ['smoke'],
        'allowed_args': {'kind': 'str'}, 'timeout_seconds': 10}]}))
    yield tmp_path, manuscript
    # Last-resort test cleanup only, never production read behaviour. Kill the
    # workload first; no test teardown kills both cleanup owners over live work.
    identities = []
    for name in ('worker.identity', 'producer.identity'):
        path = manuscript / name
        if path.is_file():
            identities.append(json.loads(path.read_text()))
    for job_path in (manuscript / 'research_runs').glob('run-*.json'):
        if job_path.name.endswith('.receipt.json'): continue
        try:
            job = json.loads(job_path.read_text())
            Path(job['cancel_path']).touch()
            receipt=job_path.with_name(job_path.stem+'.receipt.json')
            if receipt.is_file():job.update(runner.validated_receipt(job,json.loads(receipt.read_text())))
            identities += list((job.get('supervision') or {}).get('roles', {}).values())
        except (OSError, ValueError, KeyError): pass
    for ident in identities:
        try: runner._signal(ident, signal.SIGKILL)
        except OSError: pass


def launch(project, kind='sleep', timeout=10):
    root, manuscript = project
    config = manuscript / 'research_producers.json'
    value = json.loads(config.read_text());value['producers'][0]['timeout_seconds'] = timeout
    config.write_text(json.dumps(value))
    status, value = research_runs.launch('fixture', {'producer_id': 'bounded', 'mode': 'smoke',
                                        'args': {'kind': kind}}, root)
    assert status == 202, value
    job_path = manuscript / 'research_runs' / (value['run']['id'] + '.json')
    job = wait_for(lambda: research_runs._run_status(manuscript,job_path.stem),
                   lambda x: x and len((x.get('supervision') or {}).get('roles', {})) == 2)
    wait_for(lambda: (manuscript / 'worker.pid').is_file())
    worker = runner._identity(int((manuscript / 'worker.pid').read_text()))
    return job_path, job, worker


def settled(job_path):
    receipt = wait_for(lambda: json.loads(job_path.with_name(job_path.stem + '.receipt.json').read_text()),
                       lambda value:value and (value.get('supervision') or {}).get('phase')=='TERMINAL')
    assert receipt['cleanup']['status'] == 'VERIFIED', receipt
    assert not receipt['cleanup']['remaining']
    return receipt


def test_real_cancel_cleans_escaped_session_and_followup(project):
    root, manuscript = project
    path, job, worker = launch(project)
    assert research_runs.active_runs(root)[0]['id'] == job['id']
    status, _, body = rs.handle('/research/cancel', {}, 'POST',
        json.dumps({'project': 'fixture', 'id': job['id']}).encode(), repo_root=root)
    assert status == 202, body
    start = time.monotonic(); receipt = settled(path)
    assert receipt['state'] == 'CANCELLED' and receipt['exit_code'] is not None
    assert time.monotonic() - start < 7
    assert runner.identity_state(worker) == 'DEAD'
    assert research_runs.active_runs(root) == []
    assert [row['id'] for row in json.loads((path.parent/'index.json').read_text())['pending_supervision']]==[job['id']]
    for name in ('worker.pid', 'producer.pid'): (manuscript / name).unlink()
    second, _, child = launch(project, 'exit')
    assert settled(second)['state'] == 'COMPLETE'
    assert runner.identity_state(child) == 'DEAD'
    assert job['id'] not in [row['id'] for row in json.loads((path.parent/'index.json').read_text())['pending_supervision']]


@pytest.mark.parametrize('kind', ['exit', 'double'])
def test_normal_exit_and_deadline_cannot_leave_setsid_or_doublefork(project, kind):
    path, job, worker = launch(project, kind, timeout=1)
    receipt = settled(path)
    assert receipt['state'] == ('COMPLETE' if kind == 'exit' else 'TIMED_OUT')
    assert runner.identity_state(worker) == 'DEAD'
    assert receipt['cleanup']['seconds'] <= 6.5
    assert receipt['cleanup']['metrics']['tree_visits'] < 10000


@pytest.mark.parametrize('lost', ['guardian', 'supervisor'])
def test_single_owner_sigkill_survivor_cleans_and_publishes(project, lost):
    root, _ = project
    path, job, worker = launch(project)
    roles = job['supervision']['roles']
    assert runner._signal(roles[lost], signal.SIGKILL)
    receipt = settled(path)
    assert receipt['execution_state'] == 'FAILED'
    assert lost + '-lost' in receipt['causes']
    assert receipt['publisher']['role'] == ('supervisor' if lost == 'guardian' else 'guardian')
    assert runner.identity_state(worker) == 'DEAD'
    assert research_runs.active_runs(root) == []


def test_strict_pid_mismatch_never_signals_unrelated_task():
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])
    try:
        actual = runner._identity(process.pid)
        assert runner._signal({**actual, 'start_token': 'wrong-boot-or-start'}, signal.SIGKILL) is False
        assert runner._signal({'pid':process.pid}, signal.SIGKILL) is False
        assert process.poll() is None
    finally:
        process.kill();process.wait()


def test_pending_cold_health_survives_missing_owners_and_bad_metadata(project, monkeypatch):
    root, manuscript = project
    runs = manuscript / 'research_runs';runs.mkdir()
    job_path = runs / 'run-lost.json'
    job = {'id':'run-lost','project':'fixture','launch_token':'exact-token','state':'RUNNING',
           'supervision':{'schema_version':runner.SCHEMA,'roles':{
               'guardian':{'pid':99999999,'start_token':'not-current'},
               'supervisor':{'pid':99999998,'start_token':'not-current'}}}}
    job_path.write_text(json.dumps(job))
    handle = {'id':'run-lost','project':'fixture','launch_token':'exact-token',
              'job_path':job_path.relative_to(root).as_posix()}
    index_path = runs / 'index.json'
    index_path.write_text(json.dumps({'runs':['run-lost'],'pending_supervision':[handle],
                                      'run_handles':{'run-lost':handle}}))
    monkeypatch.setattr(research_observation, '_digest', lambda *_a, **_k: pytest.fail('health hashed historical/result body'))
    monkeypatch.setattr(research_runs, '_run_status', lambda *_a, **_k: pytest.fail('health hydrated rich run status'))
    rows = research_runs.active_runs(root)
    assert len(rows) == 1 and rows[0]['state'] == 'CLEANUP_UNRESOLVED'
    job_path.write_text('{broken')
    assert research_runs.active_runs(root)[0]['cleanup']['status'] == 'UNKNOWN'
    index_path.write_text('{broken')
    assert research_runs.active_runs(root)[0]['id'] == 'index'
    index_path.unlink()
    assert research_runs.active_runs(root)[0]['id'] == 'index'


def test_unverified_terminal_is_not_complete_or_idle(project):
    root, manuscript = project
    runs = manuscript / 'research_runs';runs.mkdir()
    handle={'id':'run-one','project':'fixture','launch_token':'token',
            'job_path':'fixture/manuscript/research_runs/run-one.json'}
    job={**handle,'state':'RUNNING','result_absolute':str(runs/'result.json'),
         'supervision':{'schema_version':runner.SCHEMA,'roles':{}}}
    (runs/'run-one.json').write_text(json.dumps(job))
    (runs/'index.json').write_text(json.dumps({'runs':['run-one'],'pending_supervision':[handle],
                                              'run_handles':{'run-one':handle}}))
    (runs/'run-one.receipt.json').write_text(json.dumps({'state':'COMPLETE',
         'supervision_schema':runner.SCHEMA,'launch_token':'token','cleanup':{'status':'INCOMPLETE'}}))
    assert research_runs._run_status(manuscript,'run-one')['state'] == 'CLEANUP_UNRESOLVED'
    assert research_runs.active_runs(root)[0]['state'] == 'CLEANUP_UNRESOLVED'


def test_capability_refusal_precedes_spawn_and_run_metadata(project, monkeypatch):
    root, manuscript = project
    monkeypatch.setattr(runner, 'capability', lambda: {'status':'UNAVAILABLE','missing':['controlled']})
    monkeypatch.setattr(research_runs.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('unsupported producer spawned'))
    status, body = research_runs.launch('fixture', {'producer_id':'bounded','mode':'smoke','args':{}}, root)
    assert status == 503 and body['supervision_capability']['missing'] == ['controlled']
    assert not (manuscript/'research_runs').exists()


def test_completed_run_locator_survives_selected_home_change(project, monkeypatch):
    root, manuscript = project
    path, job, worker = launch(project, 'exit')
    assert settled(path)['state'] == 'COMPLETE'
    other = manuscript.parent/'other';other.mkdir()
    item, _ = research_context.project('fixture', root)
    monkeypatch.setattr(research_context, 'project', lambda _p, _r: (item,other))
    status, _, body = rs.handle('/research/run/status', {'project':['fixture'],'id':[job['id']]},
                                'GET', b'', repo_root=root)
    assert status == 200 and json.loads(body)['state'] == 'COMPLETE'
    index = path.parent/'index.json'; value=json.loads(index.read_text())
    value['run_handles'][job['id']]['launch_token']='different'
    index.write_text(json.dumps(value))
    status, _, body=rs.handle('/research/run/status',{'project':['fixture'],'id':[job['id']]},
                              'GET',b'',repo_root=root)
    assert status == 200 and json.loads(body)['state']=='UNAVAILABLE'


def test_detached_short_lived_launcher_does_not_own_execution(project):
    root, manuscript = project
    # Actual app owner in a process which exits as soon as admission returns.
    code="from laplace.web.research_surface import launch; from pathlib import Path; import json; s,v=launch('fixture',{'producer_id':'bounded','mode':'smoke','args':{'kind':'exit'}},Path(%r)); print(json.dumps(v['run'])); assert s==202" % str(root)
    completed = subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True,timeout=5)
    job=json.loads(completed.stdout)
    path=manuscript/'research_runs'/(job['id']+'.json')
    assert settled(path)['state']=='COMPLETE'
    worker=runner._identity(int((manuscript/'worker.pid').read_text()))
    assert worker is None or runner.identity_state(worker)=='DEAD'


@pytest.mark.parametrize('lost', ['guardian','supervisor'])
def test_owner_death_before_readiness_never_admits_producer(project, monkeypatch, lost):
    root, manuscript = project
    marker, release = manuscript/'ready-paused', manuscript/'ready-release'
    original = subprocess.Popen
    bootstrap = """import time
from pathlib import Path
from laplace.research import research_runner as r
send=r._Channel.send
def paused(self,row):
    if row.get('kind')=='ready':
        Path(%r).touch()
        while not Path(%r).exists(): time.sleep(.01)
    return send(self,row)
r._Channel.send=paused
r.main()
""" % (str(marker),str(release))
    def launch_paused(argv, **kwargs):
        if argv[1:3] == ['-m','laplace.research.research_runner']:
            argv=[argv[0],'-c',bootstrap,*argv[3:]]
        return original(argv,**kwargs)
    monkeypatch.setattr(research_runs.subprocess,'Popen',launch_paused)
    status, out=research_runs.launch('fixture',{'producer_id':'bounded','mode':'smoke','args':{}},root)
    assert status==202
    path=manuscript/'research_runs'/(out['run']['id']+'.json')
    wait_for(marker.exists)
    job=research_runs._run_status(manuscript,path.stem)
    assert runner._signal(job['supervision']['roles'][lost],signal.SIGKILL)
    release.touch()
    receipt=settled(path)
    assert receipt['state']=='FAILED'
    assert not (manuscript/'producer.pid').exists()
    assert receipt['cleanup']['observed_count'] <= 1


def test_producer_sigkill_still_cleans_adopted_workers(project):
    path, job, worker=launch(project)
    job=wait_for(lambda:research_runs._run_status(project[1],path.stem),lambda d:d and d.get('producer_identity'))
    assert runner._signal(job['producer_identity'],signal.SIGKILL)
    receipt=settled(path)
    assert receipt['state']=='FAILED' and receipt['exit_code']==-signal.SIGKILL
    assert runner.identity_state(worker)=='DEAD'


def test_owned_index_and_active_reason_flow_through_existing_health_projection(project):
    from laplace.writing import turn_jobs
    root, manuscript=project
    runs=manuscript/'research_runs';runs.mkdir()
    (runs/'index.json').write_text('{bad')
    active=research_runs.active_runs(root)
    rows, omitted=turn_jobs.active_work_projection(active)
    observed=next(row for row in rows if row.get('kind')=='research-run')
    assert observed['cleanup']['status']=='UNKNOWN' and observed['state']=='CLEANUP_UNRESOLVED'
    assert 'index' in observed['reason'] and observed['job_path'].endswith('index.json')


def test_fixed_primary_reason_retains_simultaneous_causes(tmp_path):
    result=tmp_path/'not-produced.json'
    cleanup={'status':'VERIFIED','issues':[],'remaining':[]}
    value=runner._execution_receipt({'result_absolute':str(result)},None,None,
                                    ['timeout','cancelled','timeout'],cleanup)
    assert value['state']=='CANCELLED' and value['causes']==['timeout','cancelled']


def test_metadata_failure_does_not_skip_physical_cleanup(project):
    root, manuscript=project
    path, job, worker=launch(project)
    # Corrupt only the already-admitted job metadata. Both real owners retain
    # their private admitted identity/deadline cut; neither may skip retirement.
    path.write_text('{broken')
    Path(job['cancel_path']).touch()
    wait_for(lambda:runner.identity_state(worker),lambda value:value=='DEAD')
    rows=research_runs.active_runs(root)
    assert len(rows)==1 and rows[0]['cleanup']['status']=='UNKNOWN'
    progress=json.loads(path.with_name(path.stem+'.receipt.json').read_text())
    assert progress['supervision']['phase']!='TERMINAL'


def test_legacy_terminal_rows_stay_historical_without_body_hydration(project, monkeypatch):
    root, manuscript=project
    runs=manuscript/'research_runs';runs.mkdir()
    (runs/'index.json').write_text(json.dumps({'runs':['run-old']}))
    (runs/'run-old.json').write_text(json.dumps({'id':'run-old','project':'fixture'}))
    (runs/'run-old.receipt.json').write_text(json.dumps({'state':'COMPLETE','result_sha256':'historical'}))
    original=research_observation._read_object
    def bounded(path,*args,**kwargs):
        if path.name in {'run-old.json','run-old.receipt.json'}:
            pytest.fail('health hydrated terminal history')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(research_observation,'_read_object',bounded)
    assert research_runs.active_runs(root)==[]


def test_launch_and_baseline_use_declared_index_before_selected_home_activation(project, monkeypatch):
    from laplace.writing import mutation_attribution
    root, manuscript=project
    item,_=research_context.project('fixture',root)
    other=manuscript.parent/'other';other.mkdir()
    (other/'producer.py').write_text(PRODUCER)
    (other/'research_producers.json').write_bytes((manuscript/'research_producers.json').read_bytes())
    monkeypatch.setattr(research_context,'project',lambda _p,_r:(item,other))
    footprint=mutation_attribution._mutation_file_snapshot(root,'fixture',operation='experiment_run')
    key='fixture/manuscript/research_runs/index.json'
    assert key in footprint and footprint[key] is None
    status,out=research_runs.launch('fixture',{'producer_id':'bounded','mode':'smoke','args':{'kind':'exit'}},root)
    assert status==202
    path=other/'research_runs'/(out['run']['id']+'.json')
    index=manuscript/'research_runs'/'index.json'
    assert index.is_file() and not (other/'research_runs'/'index.json').exists()
    handle=json.loads(index.read_text())['run_handles'][out['run']['id']]
    assert handle['job_path']==path.relative_to(root).as_posix()
    assert settled(path)['state']=='COMPLETE'
    assert research_runs.active_runs(root)==[]


def test_selected_metadata_costs_and_no_historical_body_reads(project, monkeypatch):
    root, manuscript=project
    path,job,worker=launch(project)
    roles=job['supervision']['roles']
    resources={}
    for role,identity in roles.items():
        proc=Path('/proc')/str(identity['pid'])
        status=dict(line.split(':',1) for line in (proc/'status').read_text().splitlines() if ':' in line)
        resources[role]={'fd_count':len(list((proc/'fd').iterdir())),
                         'rss_kib':int(status['VmRSS'].split()[0])}
        assert resources[role]['fd_count']<32
    index=path.parent/'index.json';value=json.loads(index.read_text())
    value['runs'] += [f'run-historical-{i}' for i in range(1000)]
    index.write_text(json.dumps(value))
    reads=[];original=research_observation._read_object
    def observed(p,*args,**kwargs):
        if p.suffix=='.json' and p.is_file(): reads.append((p.name,p.stat().st_size))
        assert not p.name.startswith('run-historical-')
        return original(p,*args,**kwargs)
    monkeypatch.setattr(research_observation,'_read_object',observed)
    monkeypatch.setattr(research_observation,'_digest',lambda *_a,**_k:pytest.fail('health hashed result/scientific input'))
    timings=[];counts=[]
    for _ in range(3):
        reads.clear();start=time.perf_counter();active=research_runs.active_runs(root)
        timings.append(time.perf_counter()-start);counts.append({'files':len(reads),'bytes':sum(n for _,n in reads)})
        assert [row['id'] for row in active]==[job['id']]
        assert len(reads)==3  # index, immutable launch job, selected progress; no history bodies
    Path(job['cancel_path']).touch()
    receipt=settled(path)
    print(json.dumps({'health_seconds':timings,'metadata':counts,'owners':resources,
                      'cleanup':receipt['cleanup'],'job_bytes':path.stat().st_size,
                      'index_bytes':index.stat().st_size,'receipt_bytes':path.with_name(path.stem+'.receipt.json').stat().st_size},sort_keys=True))


def test_acknowledged_launch_bytes_stay_fixed_through_real_progress_and_cleanup(project):
    root,manuscript=project
    path,job,worker=launch(project)
    index=path.parent/'index.json'
    before={path:path.read_bytes(),index:index.read_bytes()}
    observed=research_runs._run_status(manuscript,job['id'])
    assert observed['producer_identity'] and observed['supervision']['phase']=='ACTIVE'
    assert all(p.read_bytes()==data for p,data in before.items())
    Path(job['cancel_path']).touch()
    settled(path)
    assert all(p.read_bytes()==data for p,data in before.items())
    # Even the trusted producer helper cannot downgrade a terminal observation.
    with pytest.raises(ValueError,match='late progress'):
        runner._update(path,job,{'supervision':{'phase':'ACTIVE'}})
    assert all(p.read_bytes()==data for p,data in before.items())


def test_runtime_receipt_cannot_override_immutable_scope_or_provenance(project):
    root,manuscript=project
    path,job,worker=launch(project)
    receipt_path=path.with_name(path.stem+'.receipt.json')
    original=json.loads(receipt_path.read_text())
    forged={**original,'project':'another-project','producer_argv':['not admitted']}
    with pytest.raises(ValueError,match='immutable launch'):
        runner.validated_receipt(json.loads(path.read_text()),forged)
    # Scope/refusal is exercised through the actual passive owner, then the exact
    # recorded progress is restored so the real owners can finish their cleanup.
    runner.atomic_json(receipt_path,forged)
    assert research_runs._run_status(manuscript,job['id'])['state']=='CLEANUP_UNRESOLVED'
    assert research_runs.active_runs(root)[0]['cleanup']['status']=='UNKNOWN'
    runner.atomic_json(receipt_path,original)
    Path(job['cancel_path']).touch()
    settled(path)


def test_owner_pipe_backpressure_is_bounded():
    import socket
    left,right=socket.socketpair()
    left.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,4096)
    channel=runner._Channel(left)
    try:
        start=time.monotonic()
        with pytest.raises(TimeoutError):channel.send({'bounded':'x'*100000})
        assert time.monotonic()-start<.6
    finally:
        channel.close();right.close()


@pytest.mark.parametrize('cancel',[False,True])
def test_stopped_supervisor_cannot_defeat_guardian_cutoff_or_cancel(project,cancel):
    root,manuscript=project
    path,job,worker=launch(project,timeout=1)
    assert runner._signal(job['supervision']['roles']['supervisor'],signal.SIGSTOP)
    start=time.monotonic()
    if cancel:
        status,_,_=rs.handle('/research/cancel',{},'POST',
            json.dumps({'project':'fixture','id':job['id']}).encode(),repo_root=root)
        assert status==202
    receipt=settled(path)
    assert time.monotonic()-start<7
    assert receipt['state']==('CANCELLED' if cancel else 'TIMED_OUT')
    assert 'timeout' in receipt['causes']
    assert 'supervisor-unresponsive' in receipt['causes']
    assert runner.identity_state(worker)=='DEAD'
    assert research_runs.active_runs(root)==[]


def test_stopped_guardian_cannot_block_survivor_publication(project):
    root,manuscript=project
    path,job,worker=launch(project,timeout=1)
    assert runner._signal(job['supervision']['roles']['guardian'],signal.SIGSTOP)
    start=time.monotonic()
    Path(job['cancel_path']).touch()
    receipt=settled(path)
    assert time.monotonic()-start<7
    assert receipt['state']=='CANCELLED' and receipt['publisher']['role']=='supervisor'
    assert runner.identity_state(worker)=='DEAD'
    assert research_runs.active_runs(root)==[]


def test_stale_child_list_cannot_adopt_an_unrelated_reused_pid(monkeypatch):
    # Pure procfs observation model: old parent100 listed child200, but the
    # current200 belongs to999. No real process is signalled by this control.
    monkeypatch.setattr(runner.os,'getpid',lambda:100)
    monkeypatch.setattr(runner,'_identity',lambda pid:{'pid':pid,'start_token':str(pid)+'-current'})
    monkeypatch.setattr(runner,'identity_state',lambda identity:'LIVE')
    original_iter=Path.iterdir;original_read=Path.read_text
    def tasks(path):
        if str(path)=='/proc/100/task':return iter([Path('/proc/100/task/100')])
        if str(path)=='/proc/200/task':pytest.fail('unrelated replacement entered owned traversal')
        return original_iter(path)
    def contents(path,*args,**kwargs):
        if str(path)=='/proc/100/task/100/children':return '200'
        if str(path)=='/proc/200/stat':return '200 (replacement) S 999 0 0'
        return original_read(path,*args,**kwargs)
    monkeypatch.setattr(Path,'iterdir',tasks);monkeypatch.setattr(Path,'read_text',contents)
    monkeypatch.setattr(runner,'_signal',lambda *_a:pytest.fail('signalled unrelated replacement'))
    tree=runner._Tree()
    assert tree.scan()==[] and tree.known=={}


def test_reaped_status_keeps_start_identity_and_does_not_overwrite_known_code(monkeypatch):
    from types import SimpleNamespace
    observed=iter([SimpleNamespace(si_pid=200),None])
    monkeypatch.setattr(runner.os,'waitid',lambda *_a:next(observed))
    monkeypatch.setattr(runner.os,'waitpid',lambda *_a:(200,3<<8))
    monkeypatch.setattr(runner,'_identity',lambda pid:{'pid':pid,'start_token':'new-worker-start'})
    tree=runner._Tree();tree.reap()
    assert tree.exits=={(200,'new-worker-start'):3}
    producer={'pid':200,'start_token':'original-producer-start'}
    assert runner._producer_exit(None,producer,tree.exits) is None
    assert runner._producer_exit(0,producer,tree.exits)==0
    assert runner._producer_exit(None,{'pid':200,'start_token':'new-worker-start'},tree.exits)==3
    # The real normal-exit case below also retains producer0 while a worker's
    # nonzero waited status is recorded in the same cleanup observation.


def test_unsupported_platform_import_reaches_named_capability_without_fcntl():
    code="import sys,subprocess,socket; sys.platform='darwin'; sys.modules['fcntl']=None; from laplace.research.research_runner import capability; c=capability(); assert c['status']=='UNAVAILABLE'; print(c['platform'])"
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True,timeout=5)
    assert result.stdout.strip()=='darwin'


def test_cutoff_before_supervisor_setup_has_no_admission_and_keeps_timeout(project,monkeypatch):
    root,manuscript=project
    marker,release=manuscript/'setup-paused',manuscript/'setup-release'
    original=subprocess.Popen
    bootstrap="""import os,time
from pathlib import Path
from laplace.research import research_runner as r
guardian=os.getpid();setup=r._setup
def paused():
    if os.getpid()!=guardian:
        Path(%r).touch()
        while not Path(%r).exists():time.sleep(.01)
    return setup()
r._setup=paused
r.main()
""" % (str(marker),str(release))
    def launch_paused(argv,**kwargs):
        if argv[1:3]==['-m','laplace.research.research_runner']:
            argv=[argv[0],'-c',bootstrap,*argv[3:]]
        return original(argv,**kwargs)
    monkeypatch.setattr(research_runs.subprocess,'Popen',launch_paused)
    config=manuscript/'research_producers.json';value=json.loads(config.read_text())
    value['producers'][0]['timeout_seconds']=1;config.write_text(json.dumps(value))
    status,out=research_runs.launch('fixture',{'producer_id':'bounded','mode':'smoke','args':{}},root)
    assert status==202
    path=manuscript/'research_runs'/(out['run']['id']+'.json')
    wait_for(marker.exists)
    wait_for(lambda:research_runs._run_status(manuscript,path.stem),
             lambda row:row and (row.get('supervision') or {}).get('phase')=='CLEANUP')
    release.touch()
    receipt=settled(path)
    assert receipt['state']=='TIMED_OUT' and 'timeout' in receipt['causes']
    assert not (manuscript/'producer.pid').exists()


def retained_metadata(project):
    """Synthetic historical envelope for passive parsing, not kernel proof."""
    root,manuscript=project;runs=manuscript/'research_runs';runs.mkdir()
    handle={'id':'run-retained','project':'fixture','launch_token':'retained-token',
            'job_path':'fixture/manuscript/research_runs/run-retained.json'}
    roles={'guardian':{'pid':99999991,'start_token':'guard-start'},
           'supervisor':{'pid':99999992,'start_token':'super-start'}}
    job={**handle,'state':'RUNNING','execution_deadline_monotonic':100.,
         'result_absolute':str(runs/'result.json'),
         'supervision':{'schema_version':runner.SCHEMA,'roles':{},'cleanup_limit_seconds':6.}}
    receipt={'supervision_schema':runner.SCHEMA,'launch_token':handle['launch_token'],
             'execution_deadline_monotonic':100.,'state':'FAILED','execution_state':'FAILED',
             'exit_code':3,'reason':'historical nonzero exit','roles':roles,
             'publisher':{'role':'guardian',**roles['guardian']},
             'supervision':{'schema_version':runner.SCHEMA,'phase':'TERMINAL','roles':roles,
                            'cleanup_limit_seconds':6.,'cleanup_deadline_monotonic':106.},
             'cleanup':{'status':'VERIFIED','remaining':[],'issues':[]}}
    path=runs/'run-retained.json';runner.atomic_json(path,job)
    target=runs/'run-retained.receipt.json';runner.atomic_json(target,receipt)
    index=runs/'index.json'
    runner.atomic_json(index,{'runs':[handle['id']],'run_handles':{handle['id']:handle},
                             'pending_supervision':[handle]})
    return root,manuscript,path,target,index,job,receipt


@pytest.mark.parametrize('field,value',[
    (('supervision','phase'),[]),(('cleanup','status'),[]),
    (('publisher','role'),[]),(('state',),[]),(('publisher',),['invalid'])])
def test_malformed_receipt_types_refuse_as_unknown_through_passive_owners(project,monkeypatch,field,value):
    root,manuscript,path,target,index,job,receipt=retained_metadata(project)
    parent=receipt
    for key in field[:-1]:parent=parent[key]
    parent[field[-1]]=value
    with pytest.raises(ValueError):runner.validated_receipt(job,receipt)
    runner.atomic_json(target,receipt)
    monkeypatch.setattr(runner,'_signal',lambda *_a:pytest.fail('passive parsing signalled'))
    status=research_runs._run_status(manuscript,path.stem)
    assert status['state']=='CLEANUP_UNRESOLVED' and status['cleanup']['status']=='UNKNOWN'
    active=research_runs.active_runs(root)
    assert len(active)==1 and active[0]['cleanup']['status']=='UNKNOWN'


@pytest.mark.parametrize('value',[[],['invalid'],'invalid',{'schema_version':[],'roles':{}}])
def test_malformed_job_supervision_is_explicit_unknown(project,monkeypatch,value):
    root,manuscript,path,target,index,job,receipt=retained_metadata(project)
    job['supervision']=value;runner.atomic_json(path,job)
    monkeypatch.setattr(runner,'_signal',lambda *_a:pytest.fail('passive parsing signalled'))
    assert research_runs._run_status(manuscript,path.stem)['cleanup']['status']=='UNKNOWN'
    assert research_runs.active_runs(root)[0]['cleanup']['status']=='UNKNOWN'


def test_malformed_pending_id_refuses_before_hashing_or_job_lookup(project):
    root,manuscript,path,target,index,job,receipt=retained_metadata(project)
    value=json.loads(index.read_text());value['pending_supervision'][0]['id']=[]
    runner.atomic_json(index,value)
    active=research_runs.active_runs(root)
    assert len(active)==1 and active[0]['id']=='index' and active[0]['cleanup']['status']=='UNKNOWN'


def test_valid_retained_receipt_remains_readable_and_nonactive(project):
    root,manuscript,path,target,index,job,receipt=retained_metadata(project)
    assert runner.validated_receipt(job,receipt)==receipt
    assert research_runs._run_status(manuscript,path.stem)['state']=='FAILED'
    assert research_runs.active_runs(root)==[]


def test_pending_reservation_capacity_is_128_and_a_full_index_changes_nothing(project):
    """S1 B7: the launch reservation (writing.research_runs._reserve_launch) admits below 128 unresolved
    pending handles and refuses at 128 before the job or the index is written."""
    from laplace.research import research_runs
    root, manuscript = project
    runs = manuscript / 'research_runs';runs.mkdir()

    def pending(count):
        for stale in runs.glob('run-*.json'):stale.unlink()
        handles = []
        for number in range(count):
            path = runs / f'run-{number:03d}.json'
            handle = {'id':path.stem,'project':'fixture','launch_token':f'token-{number}',
                      'job_path':path.relative_to(root).as_posix()}
            path.write_text(json.dumps({**handle,'state':'RUNNING'}))
            handles.append(handle)
        (runs/'index.json').write_text(json.dumps({'runs':[row['id'] for row in handles],
            'pending_supervision':handles,'run_handles':{row['id']:row for row in handles}}))

    job = {'id':'run-new','launch_token':'new-token','state':'RUNNING'}
    pending(128)
    before = (runs/'index.json').read_bytes()
    with pytest.raises(research_runs._LaunchRefused) as refused:
        research_runs._reserve_launch(root, 'fixture', job, runs/'run-new.json', runs)
    assert refused.value.status == 409 and 'capacity is full' in refused.value.body['error']
    assert (runs/'index.json').read_bytes() == before and not (runs/'run-new.json').exists()
    pending(127)
    research_runs._reserve_launch(root, 'fixture', job, runs/'run-new.json', runs)
    index = json.loads((runs/'index.json').read_text())
    assert len(index['pending_supervision']) == 128 and index['pending_supervision'][-1]['id'] == 'run-new'
    assert json.loads((runs/'run-new.json').read_text())['launch_token'] == 'new-token'
