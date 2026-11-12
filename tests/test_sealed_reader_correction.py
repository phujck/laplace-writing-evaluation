"""Only SR-R1/SR-C1 changed custody and explicit pre-admission projection controls."""
import copy
import json
from urllib.parse import urlsplit,parse_qs

import pytest

from test_sealed_text_reader import case,qualify,prepare_start
from laplace.writing import sealed_reader as S,turn_admission as T,turn_execution as E,records
from laplace.representation import writing_bodies
from laplace.native import tools
from laplace.web import authoring_http


@pytest.mark.parametrize('fault',['opaque','missing','corrupt','wrong-kind','wrong-basis','unsupported-reference'])
def test_qualification_requires_verified_retained_basis(case,monkeypatch,fault):
    root,_,_,_=case;value,payload=prepare_start(case)
    path=root/S.QUALIFICATION;proof=json.loads(path.read_text());entry=proof['evidence'][0]
    envelope=S._get(root,entry['body'])
    if fault=='opaque':
        proof['evidence']=[{'kind':kind,'sha256':'sha256:'+'a'*64} for kind in sorted(S.EVIDENCE_KINDS)]
    elif fault in {'missing','corrupt'}:
        blob=writing_bodies.store(root).key_path(envelope['observation']['content_handle'])
        if fault=='missing':blob.unlink()
        else:blob.write_bytes(b'corrupted public fixture')
    else:
        if fault=='wrong-kind':envelope['kind']='input-delivery'
        if fault=='wrong-basis':envelope['fingerprint']='sha256:'+'b'*64
        if fault=='unsupported-reference':envelope['observation']['store']='unsupported-store'
        entry['body']=S._put(root,envelope)
    path.write_text(json.dumps(proof))
    observed=S.support(root,'book');assert observed['state']!='QUALIFIED' and not observed['evidence']
    before=(root/'contract/talk.jsonl').read_bytes()
    monkeypatch.setattr(T,'new_session',lambda *a,**k:pytest.fail('Reached session effects'))
    with pytest.raises(S.NotAdmitted) as refused:T.start_turn(root,payload)
    assert refused.value.details['reader_refusal']['disposition']=='NOT_ADMITTED'
    assert [json.loads(line)['record'] for line in (root/'contract/talk.jsonl').read_bytes()[len(before):].splitlines()]==['writing-reader-refusal']
    (root/'qualification-correction-proof.json').write_text(json.dumps({'fault':fault,'support':observed,
        'refusal':refused.value.details,'actual_provider_calls':0},indent=2))


def test_valid_retained_proof_has_exact_native_and_HTTP_reads(case):
    root,_,_,_=case;value,_=prepare_start(case);support=value['support']
    assert support['state']=='QUALIFIED' and len(support['evidence'])==3
    results=[]
    for entry in support['evidence']:
        for part,read in entry['reads'].items():
            native=read['native'];result=tools.execute(root,'book','work',native['operation'],native['payload'])
            assert result['sha256']==entry[part+'_sha256']
            parsed=json.loads(result['content'])
            assert parsed['kind']==entry['kind']
            if part=='observation':assert parsed['fixture'] and parsed['actual_provider'] is False
            query=parse_qs(urlsplit(read['http']['url']).query)
            code,_,raw=authoring_http.handle(root,'/authoring/reader',query,'GET',b'')
            owner_result=json.loads(raw)
            assert code==200 and all(result[key]==item for key,item in owner_result.items())
            assert set(result)-set(owner_result)=={'review_read'}  # ordinary native project navigation
            results.append(result)
    request=support['evidence'][0]['reads']['observation']['native']['payload']['request']
    with pytest.raises(ValueError):S.request(root,{**request,'input':S._put(root,{'unrelated':'body'})})
    with pytest.raises(ValueError):S.request(root,{**request,'expected_support_basis':'sha256:'+'b'*64})
    paged=S.request(root,{**request,'offset':0,'limit':10});assert paged['next_read']
    assert paged['content']==results[1]['content'][:10]
    (root/'qualification-read-proof.json').write_text(json.dumps({'support':support,'reads':results,'page':paged},indent=2))


@pytest.mark.parametrize('fault,expected',[('support','SUPPORT_CHANGED'),('unqualified','SUPPORT_UNQUALIFIED'),
    ('source','SOURCE_CHANGED_OR_UNAVAILABLE'),('source-absent','SOURCE_CHANGED_OR_UNAVAILABLE'),
    ('task','INPUT_UNAVAILABLE'),('packet','INPUT_UNAVAILABLE'),('manifest','INPUT_UNAVAILABLE')])
def test_known_pre_session_refusals_have_exact_typed_reinspection(case,monkeypatch,fault,expected):
    root,_,_,_=case;value,payload=prepare_start(case)
    manifest=S._manifest(root,'book',value['input'])
    if fault in {'support','unqualified'}:
        (root/S.QUALIFICATION).unlink()
        if fault=='unqualified':payload['expected_support_basis']=S.support(root,'book')['support_basis']
    if fault=='source':(root/'inputs/primary.txt').write_text('Changed selected public bytes')
    if fault=='source-absent':(root/'inputs/primary.txt').unlink()
    if fault in {'task','packet'}:writing_bodies.store(root).key_path(manifest[fault]['content_handle']).unlink()
    if fault=='manifest':writing_bodies.store(root).key_path(value['manifest_id']).write_bytes(b'corrupt manifest')
    before=(root/'contract/talk.jsonl').read_bytes();original=copy.deepcopy(payload)
    monkeypatch.setattr(T,'new_session',lambda *a,**k:pytest.fail('Reached session effects'))
    monkeypatch.setattr(E,'start',lambda *a,**k:pytest.fail('Reached execution'))
    code,_,raw=authoring_http.handle(root,'/authoring/turn',{},'POST',json.dumps(payload).encode())
    answer=json.loads(raw);typed=answer['reader_refusal']
    assert code==409 and typed['code']==expected and typed['disposition']=='NOT_ADMITTED'
    assert (typed['profile'],typed['project'],typed['request_id'],typed['manifest_id'])==(
        S.PROFILE,'book',payload['request_id'],value['manifest_id'])
    assert set(typed['reinspect'])=={'support','input','currentness'}
    with pytest.raises(S.NotAdmitted) as caught:T.start_turn(root,payload)
    projected=tools.failure_response(root,'book','work','project',{'view':'sealed-text-reader'},caught.value)
    assert projected['reader_refusal']==typed
    assert [json.loads(line)['record'] for line in (root/'contract/talk.jsonl').read_bytes()[len(before):].splitlines()]==['writing-reader-refusal']
    assert typed['terminal'] and payload==original
    (root/'pre-admission-refusal-proof.json').write_text(json.dumps({'fault':fault,'HTTP':answer,
        'native_failure_projection':projected,'only_terminal_outcome_appended':True,'actual_provider_calls':0},indent=2))


def test_recorded_replay_precedes_now_missing_input_and_support(case,monkeypatch):
    root,_,_,_=case;value,payload=prepare_start(case);starts=[]
    monkeypatch.setattr(E,'start',lambda launch:starts.append(launch))
    first=T.start_turn(root,payload);assert len(starts)==1
    manifest=S._manifest(root,'book',value['input'])
    writing_bodies.store(root).key_path(manifest['packet']['content_handle']).unlink()
    writing_bodies.store(root).key_path(value['manifest_id']).unlink();(root/S.QUALIFICATION).unlink()
    (root/'inputs/primary.txt').write_text('Changed after admission')
    again=T.start_turn(root,copy.deepcopy(payload))
    assert again['reused'] and first['turn_id']==again['turn_id'] and first['session_id']==again['session_id'] and len(starts)==1
    (root/'recorded-replay-proof.json').write_text(json.dumps({'first':first,'again':again,'execution_seams':1},indent=2))


@pytest.mark.parametrize('where',['preflight-IO','unexpected','post-effect'])
def test_uncertain_or_post_effect_error_is_not_typed_no_admission(case,monkeypatch,where):
    root,_,_,_=case;value,payload=prepare_start(case)
    if where=='preflight-IO':
        monkeypatch.setattr(S,'_get',lambda *a,**k:(_ for _ in ()).throw(OSError('Public fixture I/O uncertainty')))
    if where=='unexpected':
        monkeypatch.setattr(S,'support',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('Public unexpected support fault')))
    if where=='post-effect':
        monkeypatch.setattr(E,'start',lambda *a,**k:(_ for _ in ()).throw(ValueError('Public failure after actual session/turn admission')))
    code,_,raw=authoring_http.handle(root,'/authoring/turn',{},'POST',json.dumps(payload).encode())
    answer=json.loads(raw);assert 'reader_refusal' not in answer
    assert code==(409 if where=='post-effect' else 500)
    current=records.index(root).by_request.get(('book',payload['request_id']),[])
    assert bool(current)==(where=='post-effect')
    (root/'uncertain-error-proof.json').write_text(json.dumps({'where':where,'HTTP':answer,'status':code,
        'recorded':bool(current),'no_typed_not_admitted':True,'actual_provider_calls':0},indent=2))
