"""Root's terminal request and opaque reader-control reference correction only."""
import copy
import json
from urllib.parse import urlsplit,parse_qs

import pytest

from test_sealed_text_reader import case,prepare_start
from laplace.core import bodies,identity
from laplace.writing import sealed_reader as S,turn_admission as T,turn_execution as E,records,session_reads,turn_control
from laplace.representation import writing_bodies
from laplace.web import authoring_http


def HTTP(root,payload):
    code,_,raw=authoring_http.handle(root,'/authoring/turn',{},'POST',json.dumps(payload).encode())
    return code,json.loads(raw)


def test_terminal_rejection_blocks_delayed_original_after_exact_source_restored(case,monkeypatch):
    root,_,primary,_=case;value,payload=prepare_start(case);wire=copy.deepcopy(payload);starts=[]
    monkeypatch.setattr(E,'start',lambda launch:starts.append(launch))
    assert session_reads.reader_request(root,'book',payload['request_id'],value['manifest_id'])['effect']=='NONE'
    (root/'inputs/primary.txt').write_text('Temporary public source drift')
    status,refused=HTTP(root,payload);assert status==409
    terminal=refused['reader_refusal'];assert terminal['terminal'] and terminal['disposition']=='NOT_ADMITTED'
    assert terminal['code']=='SOURCE_CHANGED_OR_UNAVAILABLE'
    lookup=session_reads.reader_request(root,'book',payload['request_id'],value['manifest_id'])
    assert lookup['effect']=='NOT_ADMITTED' and lookup['receipt'] is None and lookup['reader_refusal']==terminal
    assert not {'session_id','turn_id'}&set(terminal)
    (root/'inputs/primary.txt').write_text(primary)
    late_status,late=HTTP(root,wire);assert late_status==409 and late['reader_refusal']==terminal
    assert not starts and not [row for row in records.index(root).by_project['book'] if row['record']=='writing-session' and row['id']!='WS-informed']
    changed_status,changed=HTTP(root,{**wire,'expected_support_basis':'sha256:'+'b'*64})
    assert changed_status==409 and 'reader_refusal' not in changed
    ordinary={'project':'book','request_id':wire['request_id'],'session_id':'WS-informed','mode':'work','text':'Different request kind'}
    ordinary_status,ordinary_response=HTTP(root,ordinary)
    assert ordinary_status==409 and 'reader_refusal' not in ordinary_response
    new_status,new=HTTP(root,{**wire,'request_id':'explicit-new-after-inspection'})
    assert new_status==200 and len(starts)==1 and new['turn_id']
    assert HTTP(root,wire)[1]['reader_refusal']==terminal and len(starts)==1
    (root/'terminal-delayed-original-proof.json').write_text(json.dumps({'first':refused,'lookup':lookup,
        'restored_late_copy':late,'changed_intent':changed,'cross_kind':ordinary_response,
        'explicit_new_request':new,'execution_seams':1,'actual_provider_calls':0},indent=2))


@pytest.mark.parametrize('publication',['before','after'])
def test_publication_uncertainty_does_not_fabricate_terminal_claim(case,monkeypatch,publication):
    root,_,_,_=case;value,payload=prepare_start(case);starts=[];bank=records.bank
    monkeypatch.setattr(E,'start',lambda launch:starts.append(launch))
    (root/'inputs/primary.txt').write_text('Changed public source')
    def uncertain(root,row,**kwargs):
        if row.get('record')=='writing-reader-refusal':
            if publication=='after':bank(root,row,**kwargs)
            raise OSError('Public fixture refusal publication acknowledgement uncertainty')
        return bank(root,row,**kwargs)
    monkeypatch.setattr(records,'bank',uncertain)
    code,answer=HTTP(root,payload)
    assert code==500 and 'reader_refusal' not in answer and not starts
    lookup=session_reads.reader_request(root,'book',payload['request_id'],value['manifest_id'])
    assert lookup['effect']==('NOT_ADMITTED' if publication=='after' else 'NONE')
    if publication=='after':assert HTTP(root,payload)[1]['reader_refusal']==lookup['reader_refusal']
    assert not starts
    (root/'publication-uncertainty-proof.json').write_text(json.dumps({'fault':publication,'HTTP':answer,
        'lookup':lookup,'execution_seams':0,'actual_provider_calls':0},indent=2))


@pytest.mark.parametrize('outcome',['completed','interrupted'])
def test_actual_rich_session_preserves_opaque_input_and_new_attempt_without_packet_reads(case,monkeypatch,outcome):
    root,payload,_,_=case
    if outcome=='completed':
        text='LARGE PUBLIC SELECTED INPUT\n'+'é中🌱\n'*150000
        (root/'inputs/primary.txt').write_text(text)
        payload['primary']['expected_sha256']=identity.bytes_digest(text.encode())
    value,wire=prepare_start(case);manifest=S._manifest(root,'book',value['input']);starts=[]
    monkeypatch.setattr(E,'start',lambda launch:starts.append(launch))
    answer=T.start_turn(root,wire);launch=starts[0]
    if outcome=='interrupted':turn_control.interrupt_turn(root,{'project':'book','turn_id':answer['turn_id']})
    reply={'status':outcome,'text':'Exact public report retained.','provider_stage':'fixture-after-real-admission'}
    E._bank_reply(launch,reply);E._finish(launch,reply)
    from laplace.writing.records import _fold
    with records.index_lock:_fold._CACHE.pop(str(root/'contract/talk.jsonl'),None)
    reads=[];original=writing_bodies.read_bytes
    def measured(ref,*args,**kwargs):reads.append(ref['content_handle']);return original(ref,*args,**kwargs)
    monkeypatch.setattr(writing_bodies,'read_bytes',measured)
    summary=session_reads.session_state(root,answer['session_id'],view='summary')
    full=session_reads.session_state(root,answer['session_id'],view='full')
    turn=session_reads.session_turn_detail(root,'book',answer['turn_id'],'turn')
    projection_reads=list(reads)
    forbidden={value['manifest_id'],manifest['packet']['content_handle'],*[row['body']['content_handle'] for row in manifest['inputs']]}
    assert not forbidden.intersection(projection_reads)
    assert summary['session']['reader_profile']['input']==value['input']
    assert full['session']['reader_profile']['input']==value['input'] and turn['turn']['reader_profile']['input']==value['input']
    assert bodies.is_reference(summary['session']['reader_profile']['input'])
    handle=summary['session']['reader_capabilities']['new_attempt']['http']
    query=parse_qs(urlsplit(handle['url']).query)
    code,_,raw=authoring_http.handle(root,'/authoring/reader',query,'GET',b'')
    inspected=json.loads(raw);assert code==200 and inspected['input']==value['input']
    ordinary=S._put(root,'Ordinary rich body must still resolve')
    rich=writing_bodies.resolve_fields({'record':'writing-turn','dependencies':{'ordinary':ordinary}},root)
    assert rich['dependencies']['ordinary']=='Ordinary rich body must still resolve'
    summary_bytes=len(json.dumps(summary,ensure_ascii=False).encode())
    if outcome=='completed':assert summary_bytes < manifest['sizes']['packet']['utf8_bytes']//10
    (root/'opaque-session-reference-proof.json').write_text(json.dumps({'outcome':outcome,'input':value['input'],
        'selected_packet_bytes':manifest['sizes']['packet']['utf8_bytes'],'session_summary_bytes':summary_bytes,
        'projection_body_reads':projection_reads,'selected_input_body_reads':len(forbidden.intersection(projection_reads)),
        'new_attempt':handle,'opened_input':inspected['input'],'ordinary_rich_body_resolved':True,
        'actual_provider_calls':0},indent=2))
