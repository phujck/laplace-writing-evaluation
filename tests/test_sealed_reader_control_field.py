"""Only the declared terminal reader control-field projection consequence."""
import json
from urllib.parse import urlsplit,parse_qs

from test_sealed_text_reader import case,prepare_start
from laplace.core import identity
from laplace.writing import records
from laplace.web import authoring_http
from laplace.native import tools
from laplace.writing import sealed_reader as S
from laplace.representation import writing_bodies


def test_large_rich_terminal_record_keeps_all_reinspection_handles_and_no_input_reads(case,monkeypatch):
    root,payload,_,_=case;text='LARGE PUBLIC TERMINAL INPUT\n'+'é中🌱\n'*150000
    (root/'inputs/primary.txt').write_text(text)
    payload['primary']['expected_sha256']=identity.bytes_digest(text.encode())
    selected,wire=prepare_start(case);manifest=S._manifest(root,'book',selected['input'])
    (root/'inputs/primary.txt').write_text('Changed selected source after inspection')
    code,_,raw=authoring_http.handle(root,'/authoring/turn',{},'POST',json.dumps(wire).encode())
    terminal=json.loads(raw)['reader_refusal'];assert code==409 and terminal['terminal']
    reads=[];original=writing_bodies.read_bytes
    def measured(ref,*args,**kwargs):reads.append(ref['content_handle']);return original(ref,*args,**kwargs)
    monkeypatch.setattr(writing_bodies,'read_bytes',measured)
    row=records.exact_record('book',terminal['outcome_id'],root)[0]
    projection_reads=list(reads)
    assert row['reader_refusal']==terminal
    forbidden={selected['manifest_id'],manifest['packet']['content_handle'],*[item['body']['content_handle'] for item in manifest['inputs']]}
    assert not forbidden.intersection(projection_reads)
    executed=[]
    for name,handle in row['reader_refusal']['reinspect'].items():
        parsed=urlsplit(handle['http']['url'])
        status,_,body=authoring_http.handle(root,parsed.path,parse_qs(parsed.query),'GET',b'')
        result=json.loads(body);assert status==200
        native=handle['native'];view=tools.execute(root,'book','work',native['operation'],native['payload'])
        assert all(view[key]==value for key,value in result.items())
        if name=='input':assert result['input']==selected['input']
        if name=='currentness':assert result['manifest_id']==selected['manifest_id'] and not result['unchanged']
        executed.append({'part':name,'HTTP_status':status,'native_matches_owner':True})
    row_bytes=len(json.dumps(row,ensure_ascii=False).encode())
    assert row_bytes < manifest['sizes']['packet']['utf8_bytes']//10
    (root/'terminal-control-field-proof.json').write_text(json.dumps({'input':selected['input'],
        'outcome_id':terminal['outcome_id'],'selected_packet_bytes':manifest['sizes']['packet']['utf8_bytes'],
        'rich_record_bytes':row_bytes,'projection_body_reads':projection_reads,
        'selected_input_body_reads':len(forbidden.intersection(projection_reads)),
        'exact_refusal_and_handles_preserved':True,'executed':executed,'actual_provider_calls':0},indent=2))


def test_terminal_outer_wrapper_only_and_ordinary_rich_body_resolution(case,monkeypatch):
    root,_,_,_=case;selected,_wire=prepare_start(case)
    metadata={'reinspect':{'input':S.handle('book',view='input',input=selected['input'])},
        'reference':selected['input']}
    wrapper=S._put(root,metadata);reads=[];original=writing_bodies.read_bytes
    def measured(ref,*args,**kwargs):reads.append(ref['content_handle']);return original(ref,*args,**kwargs)
    monkeypatch.setattr(writing_bodies,'read_bytes',measured)
    resolved=writing_bodies.resolve_fields({'record':'writing-reader-refusal','reader_refusal':wrapper},root)
    assert resolved['reader_refusal']==metadata and reads==[wrapper['content_handle']]
    ordinary=S._put(root,'Ordinary rich content stays resolved')
    rich=writing_bodies.resolve_fields({'record':'writing-turn','dependencies':{'ordinary':ordinary}},root)
    assert rich['dependencies']['ordinary']=='Ordinary rich content stays resolved'
    (root/'outer-wrapper-rich-control-proof.json').write_text(json.dumps({'wrapper':wrapper,
        'nested_input':selected['input'],'body_reads':reads,'ordinary_rich_body_resolved':True,
        'actual_provider_calls':0},indent=2))
