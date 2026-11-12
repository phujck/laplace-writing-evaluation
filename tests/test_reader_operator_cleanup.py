"""Only post-spawn setup/delivery ownership and successful delivery control."""
import json
import sys
import time

import pytest

from test_reader_qualification import case,selected_commission
from laplace.writing import turn_admission as T,turn_jobs,records,provider,child_hosts


@pytest.mark.parametrize('stage',['publication','success'])
def test_spawn_lifetime_reaps_before_job_done_and_keeps_delivery_facts(case,monkeypatch,stage):
    root,_,_,_=case;_selected,value=selected_commission(case,wall_seconds=2,cleanup_grace_seconds=.1)
    script=root/'public_fake_cli.py';ready=root/'ready'
    script.write_text("""import json,signal,sys,time
from pathlib import Path
signal.signal(signal.SIGTERM,signal.SIG_IGN)
Path(%r).write_text('ready')
sys.stdin.read()
if sys.argv[1]=='output':
 print(json.dumps({'type':'system','subtype':'init','session_id':'public-native','model':'fixture-reader','tools':[],'mcp_servers':[]}),flush=True)
 print(json.dumps({'type':'result','subtype':'success','result':'Public successful delivery control.'}),flush=True)
else:
 while True:time.sleep(.05)
""" % str(ready))
    real=provider.subprocess.Popen;processes=[]
    def harmless(argv,**kwargs):
        process=real([sys.executable,str(script),'silent' if stage=='publication' else 'output'],**kwargs)
        processes.append(process);deadline=time.monotonic()+2
        while not ready.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.01)
        assert ready.exists();return process
    monkeypatch.setattr(provider.subprocess,'Popen',harmless)
    if stage=='publication':
        register=child_hosts._register_child_process
        def failed_registration(*args,**kwargs):
            register(*args,**kwargs)
            raise RuntimeError('PUBLIC original spawn publication failure')
        monkeypatch.setattr(child_hosts,'_register_child_process',failed_registration)
    answer=T.start_reader_qualification(root,value);job=turn_jobs._JOBS[answer['turn_id']]
    deadline=time.monotonic()+5
    try:
        with job['condition']:
            while not job['done'] and time.monotonic()<deadline:job['condition'].wait(.05)
        assert job['done'] and len(processes)==1
        dead_before_observed_job_done=processes[0].poll() is not None
        assert dead_before_observed_job_done
        reply=records.fold_records(root)['turns'][answer['turn_id']]['reply']
        state=reply['reader_qualification']['input_delivery']
        if stage=='publication':
            assert reply['status']=='failed' and 'PUBLIC original spawn publication failure' in reply['error']
            assert state=='PREPARED'
        else:
            assert reply['status']=='completed' and reply['text']=='Public successful delivery control.' and state=='SENT'
            assert processes[0].returncode==0
        (root/'spawn-lifetime-proof.json').write_text(json.dumps({'stage':stage,'answer':answer,'reply':reply,
            'job_done':job['done'],'owned_child_dead_and_reaped_at_job_done':dead_before_observed_job_done,
            'owned_PID':processes[0].pid,'returncode':processes[0].returncode,
            'harmless_python_children':1,'actual_provider_calls':0},indent=2))
    finally:
        for process in processes:
            if process.poll() is None:process.kill()
            process.wait(timeout=2)
