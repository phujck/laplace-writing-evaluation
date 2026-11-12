from laplace.writing import records as record_owner
"""Human current-help inspection shares native rendering, without read custody."""
from laplace.representation import writing_bodies as bodies
import json
from urllib.parse import parse_qs, urlencode

import pytest
from jsonschema import Draft202012Validator
from laplace.web import authoring as a
from laplace.work import author_history_metrics as metadata
from laplace.writing import session_reads
from laplace.native import tools, declarations as d


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path/'contract').mkdir()
    (tmp_path/'proj').mkdir()
    (tmp_path/'proj/main.tex').write_text('exact source unchanged\n')
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{
        'name':'p','kind':'project','project_dir':'proj'}]}))
    record_owner.bank(tmp_path,{'record':'writing-session','id':'WS-help','project':'p'})
    record_owner.bank(tmp_path,{'record':'writing-turn','id':'WT-help','session_id':'WS-help','project':'p','mode':'review'})
    monkeypatch.setattr(a,'_root',lambda:tmp_path)
    return tmp_path


def get(query):
    code, kind, body = a.handle('/authoring/help', query, 'GET', b'')
    assert kind.startswith('application/json')
    return code, json.loads(body)


def query(**fields):
    return parse_qs(urlencode(fields), keep_blank_values=True)


@pytest.mark.parametrize('selector',[
    {'operation':'author_history'},
    {'operation':'run_status'},
    {'operation':'run_cancel'},
    {'operation':'repository','variant':'read','context':{'path':'proj/main.tex'}},
    {'concept':'technical-friction@project'}, {},
])
def test_actual_http_matches_native_current_help_with_no_history_body_reads(project,monkeypatch,selector):
    # Warm bounded metadata first, then prohibit rich fold / exact history bodies.
    metadata.index(project)
    def forbidden(*args,**kwargs):raise AssertionError('unrelated history body opened')
    monkeypatch.setattr(session_reads,'_records',forbidden)
    monkeypatch.setattr(bodies,'resolve_fields',forbidden)
    native=tools.execute(project,'p','review','help',selector)
    # Native execute intentionally records its original read; only the human
    # adapter is observational. Capture the bytes after that native occurrence.
    before={p.relative_to(project):p.read_bytes() for p in project.rglob('*') if p.is_file()}
    encoded={**selector}
    if 'context' in encoded:encoded['context']=json.dumps(encoded['context'])
    code, body=get(query(project='p',turn_id='WT-help',**encoded))
    assert code==200 and body['help']==native
    assert body['inspection']=={'binding':'recorded-turn','turn_id':'WT-help','mode':'review'}
    assert before=={p.relative_to(project):p.read_bytes() for p in project.rglob('*') if p.is_file()}


@pytest.mark.parametrize('fields',[
    {'project':'p'}, {'project':'p','turn_id':'WT-help','mode':'review'},
    {'project':'p','turn_id':'WT-help','operation':'author_history','concept':'technical-friction@project'},
    {'project':'p','turn_id':'WT-help','verb':'read'},
    {'project':'p','turn_id':'WT-help','context':'[]','operation':'source'},
    {'project':'p','turn_id':'WT-help','context':'{"file":"a","file":"b"}','operation':'source'},
    {'project':'p','turn_id':'WT-help','context':'{"line_start":true}','operation':'source'},
    {'project':'p','turn_id':'WT-help','variant':'read'},
    {'project':'p','turn_id':'WT-help','operation':'not-deployed'},
    {'project':'p','turn_id':'not-saved'},
    {'project':'other','turn_id':'WT-help'},
    {'project':'p','mode':'unsupported'},
])
def test_refusal_precedes_help_render(project,monkeypatch,fields):
    monkeypatch.setattr(tools,'help_response',lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('rendered refusal')))
    # Semantic selector names are validated by shared renderer normally; retain
    # that validator while replacing only rendering for these malformed cases.
    original=d.validate_help_request
    def guarded(*args,**kwargs):
        original(args[3])
        raise AssertionError('rendered refusal')
    monkeypatch.setattr(tools,'help_response',guarded)
    assert get(query(**fields))[0]==409


def test_duplicate_unknown_and_wrong_turn_scope_do_not_read_or_render(project,monkeypatch):
    metadata.index(project)
    monkeypatch.setattr(tools,'help_response',lambda *args:(_ for _ in ()).throw(AssertionError('rendered')))
    for key in ('project','turn_id','operation','context'):
        value=query(project='p',turn_id='WT-help',operation='author_history')
        value[key]=['p','p']
        assert get(value)[0]==409
    record_owner.bank(project,{'record':'writing-turn','id':'OTHER','project':'other','mode':'review'})
    assert get(query(project='p',turn_id='OTHER'))[0]==409
    record_owner.bank(project,{'record':'writing-turn','id':'WT-help','project':'p','mode':'work'})
    assert get(query(project='p',turn_id='WT-help'))[0]==409


def test_unbound_human_mode_is_explicit_inspection_and_schema_parity(project):
    code,body=get(query(project='p',mode='discuss',operation='author_history'))
    assert code==200
    assert body['inspection']=={'binding':'unbound-human','turn_id':None,'mode':'discuss'}
    contract=d.HTTP_DECLARATIONS['authoring/help'].payload
    valid={'project':'p','turn_id':'WT-help','operation':'repository','variant':'read','context':{'path':'x'}}
    Draft202012Validator(contract).validate(valid)
    for changes in ({'concept':'other'},{'mode':'work'},{'unknown':True}):
        assert list(Draft202012Validator(contract).iter_errors({**valid,**changes}))


def test_original_turn_binding_is_one_index_lookup_independent_of_unrelated_bodies(project, monkeypatch):
    for n in range(40):
        record_owner.bank(project, {'record':'writing-reply','id':f'WR-unrelated-{n}',
            'project':'other','turn_id':'WT-other','text':'unrelated prose '*900})
    metadata.index(project)
    observed=[]
    real_index=record_owner.index
    monkeypatch.setattr(record_owner,'index',lambda *args,**kwargs:(observed.append(1),real_index(*args,**kwargs))[1])
    selected=[]
    real_raw=record_owner._index._raw_indexed_record
    monkeypatch.setattr(record_owner._index,'_raw_indexed_record',lambda idx,row:(selected.append(row['id']),real_raw(idx,row))[1])
    monkeypatch.setattr(session_reads,'_records',lambda *args:(_ for _ in ()).throw(AssertionError('rich fold')))
    before=(project/'contract/talk.jsonl').read_bytes()
    assert get(query(project='p',turn_id='WT-help',operation='author_history'))[0]==200
    assert observed==[1] and selected==['WT-help'] and (project/'contract/talk.jsonl').read_bytes()==before


def test_native_recorded_read_has_occurrence_but_human_inspection_does_not(project):
    native=tools.execute(project,'p','review','help',{'operation':'author_history'},turn_id='WT-help')
    receipt=native.pop('read_receipt')
    assert receipt['turn_id']=='WT-help' and receipt['operation']=='help'
    before=(project/'contract/talk.jsonl').read_bytes()
    code,body=get(query(project='p',turn_id='WT-help',operation='author_history'))
    assert code==200 and body['help']==native
    assert (project/'contract/talk.jsonl').read_bytes()==before


def test_indexed_original_turn_hash_is_verified_after_middle_rewrite_and_append(project):
    path=project/'contract/talk.jsonl'
    # Real-shaped middle line outside the index's cheap prefix/tail witnesses.
    rows=[{'record':'writing-session','id':'padding-start','project':'p','padding':'x'*12000},
          {'record':'writing-turn','id':'WT-middle','project':'p','mode':'review'},
          {'record':'writing-session','id':'padding-end','project':'p','padding':'y'*12000}]
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    metadata.index(project)
    path.write_bytes(path.read_bytes().replace(b'"mode": "review"',b'"mode": "revise"')+b'{"record":"writing-session","id":"append","project":"p"}\n')
    code,body=get(query(project='p',turn_id='WT-middle',operation='author_history'))
    assert code==409 and 'selected journal row changed' in body['error']
    code,body=get(query(project='p',turn_id='WT-middle',operation='author_history'))
    assert code==200 and body['inspection']['mode']=='revise'


def scanner_get(path):
    from laplace.web import scanner
    # Execute the actual intake with an in-memory response sink; no service or
    # provider process, alternate dispatcher or copied URL parser is involved.
    kind=scanner.make_handler()
    handler=kind.__new__(kind)
    handler.path=path
    responses=[]
    handler._send=lambda *args:responses.append(args)
    handler.do_GET()
    assert len(responses)==1
    return responses[0][0],json.loads(responses[0][1])


def test_actual_scanner_preserves_blank_help_fields_but_legacy_work_defaults(project,monkeypatch):
    assert scanner_get('/authoring/help?project=p&turn_id=WT-help&operation=author_history')[0]==200
    for suffix in ('&unknown=', '&project=', '&operation=', '&turn_id='):
        assert scanner_get('/authoring/help?project=p&turn_id=WT-help&operation=author_history'+suffix)[0]==409
    from laplace.web import project_work_surface
    seen=[]
    real_handle=project_work_surface.handle
    def read_work(path, values, method, body, **kwargs):
        seen.append(values)
        return real_handle(path,values,method,body,repo_root=project)
    monkeypatch.setattr(project_work_surface,'handle',read_work)
    code,value=scanner_get('/work/state?project=p&view=')
    assert code==200 and value['view']=='summary' and 'view' not in seen[0]


def test_declared_transport_policy_refuses_ambiguous_or_invalid_metadata(monkeypatch):
    from dataclasses import replace
    declared=d.HTTP_DECLARATIONS['authoring/help']
    assert d.http_help('/authoring/help','GET')['lossless_query'] is True
    monkeypatch.setitem(d.HTTP_DECLARATIONS,'test-duplicate',replace(declared,extras={}))
    with pytest.raises(ValueError,match='Ambiguous declared query policy'):
        d.http_lossless_query('/authoring/help','GET')
    monkeypatch.setitem(d.HTTP_DECLARATIONS,'test-duplicate',replace(declared,extras={'lossless_query':'yes'}))
    with pytest.raises(ValueError,match='Invalid declared query policy'):
        d.http_lossless_query('/authoring/help','GET')
