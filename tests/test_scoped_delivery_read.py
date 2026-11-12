"""Withheld task projections have exact executable same-owner recovery reads."""
import json
import shutil
from urllib.parse import parse_qs,urlsplit

import pytest

from laplace.manuscript import project_structure
from laplace.web import project_work_surface
from laplace.native import tools as writing_tools
from laplace.writing import records as writing_records
from laplace.writing import turn_context
from laplace.writing.records import _fold as records_fold
from laplace.writing import turn_jobs
from laplace.pipeline import authoring
from test_manuscript_structure import _section_fixture
from test_context_delta import _project as source_project


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE',str(tmp_path/'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES',str(tmp_path/'workspaces'))
    records_fold._CACHE.clear();turn_jobs._JOBS.clear()
    yield
    records_fold._CACHE.clear();turn_jobs._JOBS.clear()
    shutil.rmtree(tmp_path,ignore_errors=True)


def context(root,section='first'):
    return authoring.build_context('book',{'section_ids':[section]},root,include_guidance=False)


def test_exact_projection_bytes_and_token_recover_through_native_and_http(tmp_path):
    _section_fixture(tmp_path)
    value=context(tmp_path)
    state_path,_=authoring._state_path('book',tmp_path)
    before=state_path.read_bytes()
    writing_records.bank(tmp_path,{'record':'writing-session','id':'WS-owner','project':'book','role':'author'})
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-owner','session_id':'WS-owner',
        'project':'book','mode':'work','text':'Read the retained task scope.'})
    checked=[]
    for part in value['parts']:
        if part['key'] not in authoring._SCOPED_DELIVERY_PARTS:
            continue
        handle=part['read']
        read=writing_tools.execute(tmp_path,'book','work',handle['operation'],handle['payload'],turn_id='WT-owner')
        assert read['text']==part['text'] and read['token']==part['token'] and read['matches_expected']
        assert read['read_receipt']['operation']=='structure'
        assert read['read_receipt']['payload']['context_id']==value['context_id']
        assert not read.get('context_refresh') and not read['context_recorded']
        url=urlsplit(handle['http']['url'])
        status,_,raw=project_work_surface.handle(url.path,parse_qs(url.query),'GET',repo_root=tmp_path)
        http=json.loads(raw)
        assert status==200 and http['text']==part['text'] and http['token']==read['token']
        assert http['receipt_materializations']==1
        checked.append(part['key'])
    assert set(checked)=={'canonical_structure','section_notes'}
    assert state_path.read_bytes()==before


def test_unchanged_scope_withholds_recoverable_compound_parts_but_changed_scope_sends_them(tmp_path):
    _section_fixture(tmp_path)
    first=context(tmp_path)
    held={row['key']:row['token'] for row in first['parts']}
    second=context(tmp_path)
    delta=turn_context.without_already_delivered(second['parts'],held)
    assert {'canonical_structure','section_notes'}.issubset({row['part'] for row in delta['withheld']})
    assert len(delta['prompt'].encode())<len(first['prompt'].encode())/5
    changed=context(tmp_path,'second')
    next_delta=turn_context.without_already_delivered(changed['parts'],held)
    assert 'canonical_structure' not in {row['part'] for row in next_delta['withheld']}
    assert next(row['text'] for row in changed['parts'] if row['key']=='canonical_structure') in next_delta['prompt']


def test_changed_inputs_read_current_content_without_blessing_old_token(tmp_path):
    manuscript,_,_=_section_fixture(tmp_path)
    old=next(row for row in context(tmp_path)['parts'] if row['key']=='canonical_structure')
    plan_path=manuscript/'projection_plan.json'
    plan=json.loads(plan_path.read_text());plan['sections'][0]['title']='Revised reader purpose'
    plan_path.write_text(json.dumps(plan))
    read=project_structure.read('book',old['read']['payload'],tmp_path)
    assert not read['matches_expected'] and read['currentness']=='CHANGED_CURRENT_CONTENT'
    assert 'Revised reader purpose' in read['text']
    assert read['expected_token']==old['token'] and read['token']!=old['token']
    assert not read['historical_bytes']


def test_unknown_scope_and_crossed_part_refuse_without_guessing(tmp_path):
    _section_fixture(tmp_path)
    handle=next(row['read'] for row in context(tmp_path)['parts'] if row['key']=='canonical_structure')
    with pytest.raises(ValueError,match='unavailable'):
        project_structure.read('book',{**handle['payload'],'context_id':'CTX-'+'0'*32},tmp_path)
    with pytest.raises(ValueError,match='Delivery-part read'):
        project_structure.read('book',{**handle['payload'],'part':'all_history'},tmp_path)


def test_only_named_receipt_blobs_materialize_and_subset_cannot_write(tmp_path):
    _section_fixture(tmp_path)
    value=context(tmp_path)
    path,_=authoring._state_path('book',tmp_path)
    raw=json.loads(path.read_text())
    raw['contexts'].append({'id':'CTX-'+'1'*32,'structure':{'$laplace_context_blob':'sha256:missing'}})
    path.write_text(json.dumps(raw))
    handle=next(row['read'] for row in value['parts'] if row['key']=='canonical_structure')
    read=project_structure.read('book',handle['payload'],tmp_path)
    assert read['receipt_materializations']==1 and read['matches_expected']
    subset=authoring._read(path,'book',tmp_path,context_ids={value['context_id']})
    before=path.read_bytes()
    with pytest.raises(ValueError,match='cannot overwrite'):
        authoring._write(path,subset)
    assert path.read_bytes()==before


def test_missing_old_projection_cannot_issue_an_unrecoverable_withheld_handle(tmp_path):
    _section_fixture(tmp_path)
    first=context(tmp_path)
    path,_=authoring._state_path('book',tmp_path)
    state=json.loads(path.read_text())
    reference=state['contexts'][0]['structure']['$laplace_context_blob']
    del state['context_blobs'][reference]
    path.write_text(json.dumps(state))
    fresh=context(tmp_path)
    assert fresh['context_id']!=first['context_id']
    part=next(row for row in fresh['parts'] if row['key']=='canonical_structure')
    recovered=project_structure.read('book',part['read']['payload'],tmp_path)
    assert recovered['matches_expected'] and recovered['text']==part['text']


def test_source_only_keeps_existing_source_read_without_inventing_reader_structure(tmp_path):
    source_project(tmp_path)
    value=authoring.build_context('delta',{'files':['main.tex'],'line_start':5,'line_end':7},tmp_path,include_guidance=False)
    assert not any(part['key'] in authoring._SCOPED_DELIVERY_PARTS for part in value['parts'])
    source=next(part for part in value['parts'] if part['key'].startswith('numbered_source:'))
    read=writing_tools.execute(tmp_path,'delta','work',source['read']['operation'],source['read']['payload'])
    assert read['sources'][0]['file']=='sources/delta/main.tex'
    assert 'Paragraph line' in read['sources'][0]['text']


def test_mathematics_prerequisites_and_local_refs_keep_exact_semantics(tmp_path):
    from test_mathematical_records import project
    from laplace.research import concepts as concepts_surface
    project(tmp_path)
    revision=concepts_surface.state('paper',root=tmp_path)['revision']
    status,value=concepts_surface.change({'project':'paper','operation':'add_node','node':'thm:axiom',
        'node_kind':'theorem','essence':'Second source statement','parent':'paper://',
        'ref':'original:law.tex#thm:second','base_revision':revision},root=tmp_path)
    assert status==200
    status,_=concepts_surface.change({'project':'paper','operation':'add_edge','node':'thm:law',
        'target':'thm:axiom','rel':'prerequisite','base_revision':value['state']['revision']},root=tmp_path)
    assert status==200
    value=authoring.build_context('paper',{'node_id':'thm:law'},tmp_path,include_guidance=False)
    checked=set()
    for part in value['parts']:
        if part['key'] in authoring._SCOPED_DELIVERY_PARTS:
            read=project_structure.read('paper',part['read']['payload'],tmp_path)
            assert read['matches_expected'] and read['text']==part['text']
            checked.add(part['key'])
    assert {'mathematical_record','direct_prerequisites','local_source_refs'}<=checked
