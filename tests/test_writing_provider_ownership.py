"""Trusted spawn ownership before initialization, using inert Python processes only."""
from __future__ import annotations
import json,os,sys,subprocess
from pathlib import Path
import pytest
from laplace.web import authoring as owner
from laplace.writing import provider
from laplace.work import project_work
from laplace.writing import turn_admission
from laplace.writing import session_reads
from laplace.writing import turn_control
from laplace.writing import child_hosts
from laplace.writing import turn_jobs
from test_writing_dispatch import tree
from test_writing_dispatch_lifecycle import STUB_RUNTIME,_planned,_wait


def _binary(root):
    binary=root/'inert-codex'
    binary.write_text('#!'+sys.executable+'\nimport os,time\nfrom pathlib import Path\nPath('+repr(str(root/'inert-pids'))+').mkdir(exist_ok=True)\nPath('+repr(str(root/'inert-pids'))+',str(os.getpid())).write_text(str(os.getpid()))\ntime.sleep(60)\n')
    binary.chmod(0o700)
    return binary


def test_trusted_callback_precedes_raw_initialize_and_registration_failure_cleans_spawn(tmp_path,monkeypatch):
    binary=_binary(tmp_path);events=[];identities=[]
    def publish(process,phase):
        identities.append(child_hosts._process_identity(process.pid));events.append(('spawn',phase))
    def request(self,method,params,timeout=30):
        assert events and events[0][0]=='spawn'
        events.append(('traffic',method));return {}
    monkeypatch.setattr(provider._CodexRpcConnection,'request',request)
    conn=provider._CodexRpcConnection(tmp_path,executable=str(binary),on_spawn=publish)
    try:assert events[:2]==[('spawn','codex-rpc'),('traffic','initialize')]
    finally:conn.close()
    events.clear()
    def refuse(process,phase):
        identities.append(child_hosts._process_identity(process.pid))
        raise OSError('fixture publication failed')
    with pytest.raises(provider.ProcessRegistrationError,match='publication failed'):
        provider._CodexRpcConnection(tmp_path,executable=str(binary),on_spawn=refuse)
    assert not events and all(not child_hosts._process_matches(identity) for identity in identities)


@pytest.mark.parametrize('control',['stop','cancel'])
def test_real_blocked_raw_initialization_is_owned_before_connection_assignment(tree,monkeypatch,control):
    root=tree;runtime=root/'fixture-runtime';runtime.mkdir();binary=_binary(root)
    old="self.process=subprocess.Popen([sys.executable,'-S','-c','import time; time.sleep(60)'],start_new_session=True)"
    new="self.conn=wp._CodexRpcConnection(self.root, executable="+repr(str(binary))+", on_spawn=self.on_spawn)"
    (runtime/'sitecustomize.py').write_text(STUB_RUNTIME.replace(old,new))
    source=Path(owner.__file__).resolve().parents[1];tests=Path(__file__).resolve().parent
    env={**os.environ,'PYTHONPATH':os.pathsep.join(map(str,[runtime,source,tests])),
         'LAPLACE_STATE':str(root/'state'),'LAPLACE_TEST_PROCESS':'1'}
    parent,ident=_planned(root)
    script="import json,sys;from pathlib import Path;from laplace.web import authoring as a;print(json.dumps(a.launch_dispatch(Path(sys.argv[1]),'book','WT-parent',{'id':sys.argv[2]})))"
    result=subprocess.run([sys.executable,'-c',script,str(root),ident],env=env,cwd=root,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr
    children=json.loads(result.stdout)['children'];monkeypatch.setattr(owner,'_root',lambda:root)
    try:
        _wait(lambda:all(session_reads.child_execution(root,row['session_id']).get('provider_processes') for row in children))
        child=children[0];record=session_reads.child_execution(root,child['session_id'])
        assert record['provider_phase']=='codex-rpc' and record['active_provider_processes']
        import psutil
        psutil.Process(record['host']['pid']).kill()
        _wait(lambda:session_reads.child_execution(root,child['session_id']).get('state')=='ORPHANED')
        active=session_reads.session_state(root,child['session_id'],view='summary')['active']
        assert active['capabilities']['observation']=='snapshot' and active['capabilities']['events_url'] is None
        assert active['capabilities']['can_interrupt'] and not active['capabilities']['can_steer']
        if control=='stop':turn_control.interrupt_turn(root,{'turn_id':child['turn_id'],'project':'book'})
        else:project_work.transition('book',{'id':ident,'status':'cancelled'},root)
        _wait(lambda:not any(child_hosts._process_matches(pid) for pid in record['provider_processes']))
        if control=='stop':project_work.transition('book',{'id':ident,'status':'cancelled'},root)
        _wait(lambda:all(not session_reads.child_execution(root,row['session_id'])['active_provider_processes'] for row in children))
    finally:
        for row in children:
            record=session_reads.child_execution(root,row['session_id']);child_hosts.terminate_child_processes(record)
            child_hosts._terminate_owned_process(record.get('host') or {})


def test_ordinary_turn_provider_remains_observable_and_stoppable_after_app_host_restart(tree,monkeypatch):
    root=tree;runtime=root/'ordinary-runtime';runtime.mkdir();binary=_binary(root)
    old="self.process=subprocess.Popen([sys.executable,'-S','-c','import time; time.sleep(60)'],start_new_session=True)"
    new="self.conn=wp._CodexRpcConnection(self.root, executable="+repr(str(binary))+", on_spawn=self.on_spawn)"
    (runtime/'sitecustomize.py').write_text(STUB_RUNTIME.replace(old,new))
    source=Path(owner.__file__).resolve().parents[2]
    env={**os.environ,'PYTHONPATH':os.pathsep.join(map(str,[runtime,source,Path(__file__).resolve().parent])),
         'LAPLACE_STATE':str(root/'state'),'LAPLACE_TEST_PROCESS':'1'}
    session=turn_admission.new_session(root,'book','claude','','')
    script="""import json,sys,time
from pathlib import Path
from laplace.web import authoring as a
started=a.start_turn(Path(sys.argv[1]),{'project':'book','session_id':sys.argv[2],'mode':'work','text':'ordinary fixture'})
print(json.dumps(started),flush=True)
while any(not job['done'] for job in a._JOBS.values()):time.sleep(.1)
"""
    host=subprocess.Popen([sys.executable,'-c',script,str(root),session['id']],env=env,cwd=root,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    record={}
    try:
        started=json.loads(host.stdout.readline());monkeypatch.setattr(owner,'_root',lambda:root)
        _wait(lambda:session_reads.child_execution(root,session['id']).get('provider_processes'))
        record=session_reads.child_execution(root,session['id'])
        assert record['dispatch_id'] is None and record['turn_id']==started['turn_id']
        host.kill();host.wait(timeout=5)
        _wait(lambda:session_reads.child_execution(root,session['id'])['state']=='ORPHANED')
        assert turn_jobs.active_turn_count()==1
        assert session_reads.session_state(root,session['id'],view='summary')['active']['capabilities']['observation']=='snapshot'
        turn_control.interrupt_turn(root,{'turn_id':started['turn_id'],'project':'book'})
        _wait(lambda:not any(child_hosts._process_matches(pid) for pid in record['provider_processes']))
        assert turn_jobs.active_turn_count()==0
    finally:
        child_hosts.terminate_child_processes(record)
        if host.poll() is None:host.kill();host.wait(timeout=5)
