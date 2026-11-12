"""Operator seam only; no real CLI, proof installation or model inference."""
import copy
import json
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_sealed_text_reader import case
from laplace import sdk
from laplace.writing import sealed_reader as S,turn_admission as T,turn_execution as E,turn_jobs,records,provider
from laplace.native import tools
from laplace.web import authoring_http


def selected_commission(case,**limits):
    root,payload,_,_=case;selected=S.prepare(root,payload);current=selected['support']
    assert current['state']=='CANDIDATE' and not (root/S.QUALIFICATION).exists()
    value={'schema_version':'laplace.sealed-reader-operator-commission/1','purpose':S.OPERATOR_PURPOSE,
        'project':'book','input':selected['input'],'expected_fingerprint':current['fingerprint'],
        'expected_support_basis':current['support_basis'],'request_id':'public-operator-é',
        'limits':{'max_budget_usd':'0.50','wall_seconds':1,'cleanup_grace_seconds':.1,
            'max_input_utf8_bytes':8192,'max_output_utf8_bytes':8192,**limits}}
    return selected,value


def test_local_operator_only_uses_candidate_and_locked_exact_purpose_replay(case,monkeypatch):
    root,_,_,_=case;selected,value=selected_commission(case);launches=[]
    monkeypatch.setattr(E,'start',lambda launch:launches.append(launch))
    public={**selected['start']['payload'],'request_id':'ordinary-still-unqualified'}
    code,_,body=authoring_http.handle(root,'/authoring/turn',{},'POST',json.dumps(public).encode())
    assert code==409 and json.loads(body)['reader_refusal']['code']=='SUPPORT_UNQUALIFIED'
    with pytest.raises(ValueError):sdk.reader_start({**public,'purpose':S.OPERATOR_PURPOSE},root=root)
    with pytest.raises(ValueError):tools.execute(root,'book','work','project',{'view':'sealed-text-reader',
        'request':{'project':'book','view':'operator-qualification','commission':value}})
    first=T.start_reader_qualification(root,value);assert len(launches)==1
    profile=launches[0].reader_profile;assert profile['operator']['purpose']==S.OPERATOR_PURPOSE
    assert profile['operator']['limits']==value['limits'] and launches[0].session.get('native_id') is None
    (root/'inputs/primary.txt').write_text('Changed after actual local admission')
    again=T.start_reader_qualification(root,copy.deepcopy(value));assert again['turn_id']==first['turn_id'] and len(launches)==1
    with pytest.raises(ValueError,match='intent changed'):T.start_reader_qualification(root,{**value,'limits':{**value['limits'],'wall_seconds':2}})
    with pytest.raises(ValueError):T.start_reader_qualification(root,{**value,'purpose':'ordinary'})
    with pytest.raises(ValueError):sdk.reader_start({**selected['start']['payload'],'request_id':value['request_id']},root=root)
    assert S.support(root,'book')['state']=='CANDIDATE' and not (root/S.QUALIFICATION).exists()
    (root/'operator-admission-proof.json').write_text(json.dumps({'commission':value,'profile':profile,
        'first':first,'replay':again,'execution_seams':1,'actual_provider_calls':0},indent=2))


@pytest.mark.parametrize('field,value',[('max_budget_usd','0'),('max_budget_usd','NaN'),
    ('wall_seconds',True),('cleanup_grace_seconds',float('inf')),('max_output_utf8_bytes',0)])
def test_operator_bounds_are_closed_positive_finite_before_effects(case,monkeypatch,field,value):
    root,_,_,_=case;_selected,commission=selected_commission(case)
    commission['limits'][field]=value;before=(root/'contract/talk.jsonl').read_bytes()
    monkeypatch.setattr(T,'new_session',lambda *a,**k:pytest.fail('Session effect reached'))
    with pytest.raises(ValueError):T.start_reader_qualification(root,commission)
    assert (root/'contract/talk.jsonl').read_bytes()==before


@pytest.mark.parametrize('fault',['fingerprint','input-size','forged-input'])
def test_operator_selected_candidate_and_input_checks_precede_session(case,monkeypatch,fault):
    root,_,_,_=case;selected,value=selected_commission(case)
    if fault=='fingerprint':value['expected_fingerprint']='sha256:'+'b'*64
    if fault=='input-size':value['limits']['max_input_utf8_bytes']=1
    if fault=='forged-input':value['input']=S._put(root,{'unissued':'manifest'})
    monkeypatch.setattr(T,'new_session',lambda *a,**k:pytest.fail('Session effect reached'))
    with pytest.raises(S.NotAdmitted):T.start_reader_qualification(root,value)


def test_operator_and_production_share_exact_information_arguments(case,monkeypatch):
    root,_,_,_=case;selected,value=selected_commission(case);launches=[]
    monkeypatch.setattr(E,'start',lambda launch:launches.append(launch));T.start_reader_qualification(root,value)
    profile=launches[0].reader_profile;operator=profile['operator']
    plain=S.claude_arguments('fixture-reader','low');bounded=S.claude_arguments('fixture-reader','low',operator)
    index=bounded.index('--max-budget-usd');assert bounded[:index]+bounded[index+2:]==plain
    assert bounded[index+1]=='0.50';S.validate_arguments(bounded,'fixture-reader','low',operator)
    for extra in (['--resume','old'],['--tools','Read'],['--mcp-config','{}'],['--other']):
        with pytest.raises(ValueError):S.validate_arguments(bounded+extra,'fixture-reader','low',operator)
    assert S.execution_support(root,'book',profile)['state']=='CANDIDATE'
    with pytest.raises(ValueError):S.execution_support(root,'book',{k:v for k,v in profile.items() if k!='operator'})


def test_overlapping_operator_commission_has_one_existing_admission(case,monkeypatch):
    root,_,_,_=case;_selected,value=selected_commission(case);entered=threading.Event();release=threading.Event();starts=[]
    original=S.admit
    def gated(*args,**kwargs):entered.set();assert release.wait(3);return original(*args,**kwargs)
    monkeypatch.setattr(S,'admit',gated);monkeypatch.setattr(E,'start',lambda launch:starts.append(launch))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(T.start_reader_qualification,root,value);assert entered.wait(3)
        second=pool.submit(T.start_reader_qualification,root,copy.deepcopy(value));release.set()
        a,b=first.result(),second.result()
    assert a['turn_id']==b['turn_id'] and a['session_id']==b['session_id'] and len(starts)==1


@pytest.mark.parametrize('mode',['silent','output'])
def test_actual_existing_supervisor_stops_harmless_owned_fake_process(case,monkeypatch,mode):
    root,_,_,_=case;selected,value=selected_commission(case,wall_seconds=.25,cleanup_grace_seconds=.1,max_output_utf8_bytes=64)
    script=root/'public_fake_cli.py'
    script.write_text("""import sys,json,time,signal
signal.signal(signal.SIGTERM,signal.SIG_IGN)
sys.stdin.read()
print(json.dumps({'type':'system','subtype':'init','session_id':'public-fake-native','model':'fixture-reader','tools':[],'mcp_servers':[],'skills':[],'plugins':[]}),flush=True)
if sys.argv[1]=='output':print(json.dumps({'type':'stream_event','event':{'type':'content_block_delta','delta':{'type':'text_delta','text':'é中🌱'*10000}}}),flush=True)
while True:time.sleep(.1)
""")
    real=provider.subprocess.Popen;processes=[];argvs=[]
    def harmless(argv,**kwargs):
        assert argv[0]==str(root/'fixture-claude')
        argvs.append(argv)
        process=real([sys.executable,str(script),mode],**kwargs);processes.append(process);return process
    monkeypatch.setattr(provider.subprocess,'Popen',harmless)
    before=time.monotonic();answer=T.start_reader_qualification(root,value)
    job=turn_jobs._JOBS[answer['turn_id']]
    with job['condition']:
        while not job['done'] and time.monotonic()-before<5:job['condition'].wait(timeout=.05)
    assert job['done'] and time.monotonic()-before<5
    turn=records.fold_records(root)['turns'][answer['turn_id']];reply=turn['reply']
    expected='operator-wall-seconds' if mode=='silent' else 'operator-public-output-bytes'
    assert reply['status']=='interrupted' and reply['reader_qualification']['limit_reason']==expected
    assert len(reply['text'].encode())<=64 and len(job['text'].encode())<=64
    assert reply['delivery_receipt']['reader']['state']==S.STARTUP_STATE
    assert len(processes)==1 and processes[0].poll() is not None
    assert reply['reader_qualification']['argv']==argvs[0] and reply['reader_qualification']['input_delivery']=='SENT'
    assert reply['reader_qualification']['provider_processes'][0]['pid']==processes[0].pid
    S.validate_arguments(argvs[0][1:],'fixture-reader','low',turn['reader_profile']['operator'])
    assert S.support(root,'book')['state']=='CANDIDATE' and not (root/S.QUALIFICATION).exists()
    (root/'operator-process-proof.json').write_text(json.dumps({'mode':mode,'commission':value,'argv':argvs[0],
        'reply':reply,'process_returncode':processes[0].returncode,'elapsed_seconds':time.monotonic()-before,
        'harmless_local_python_processes':1,'actual_provider_processes':0,'actual_inference_calls':0},indent=2))
