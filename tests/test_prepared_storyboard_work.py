"""Guarded, provider-free preparation joins real Work without copying source."""
import json
import shutil
import re

import pytest

from laplace.manuscript import project_structure
from laplace.work import project_work
from laplace.writing import provider as writing_provider
from laplace.native import tools as writing_tools
from laplace.writing import session_reads
from laplace.writing import records
from laplace.writing.records import _fold as records_fold
from laplace.writing import turn_jobs
from laplace.writing import turn_admission
from laplace.writing import prepared_work, records
from laplace.writing import child_hosts
from test_manuscript_structure import _section_fixture


def _reader_visual_subjects(root):
    view=project_structure.read('book',{'view':'detail','section_ids':['first']},root)['sections'][0]
    return [view['reader_transition'],*view['paragraph_plan']['paragraphs']['items']]


def _observe_reader_visual_subjects(root):
    for subject in _reader_visual_subjects(root):
        current=project_structure.read('book',{'view':'detail','section_ids':['first'],
            **({'paragraph_id':subject['paragraph_id']} if subject.get('paragraph_id') else {})},root)['sections'][0]
        row=current['paragraph_plan']['paragraphs']['items'][0] if subject.get('paragraph_id') else current['reader_transition']
        writing_tools.execute(root,'book','work','structure_change',{
            **row['edit_action']['payload'],'changes':{},'input_observations':row['reader_basis']['inputs']})


def _visual_improvement_fixture(root):
    from test_reader_plan_owner import _rendered_reader_plot
    parent,stage=_improvement_fixture(root)
    manuscript=root/'synthetics papers/book/manuscript'
    chapter=manuscript/'chapters/chapter-01.tex'
    chapter.write_text('\\chapter{First}\n\\section{First child}\n\\chapter{Second}\n')
    data=_rendered_reader_plot(root,manuscript)
    _author_typed_reader_plan(root)
    view=project_structure.read('book',{'view':'detail','section_ids':['first']},root)['sections'][0]
    writing_tools.execute(root,'book','work','structure_change',{
        **view['reader_transition']['edit_action']['payload'],'changes':{'figures':['reader-plot']}})
    view=project_structure.read('book',{'view':'detail','section_ids':['first']},root)['sections'][0]
    row=view['paragraph_plan']['paragraphs']['items'][0]
    writing_tools.execute(root,'book','work','structure_change',{
        **row['edit_action']['payload'],'changes':{'figure_anchor':'reader-plot'}})
    _observe_reader_visual_subjects(root)
    return parent,stage,manuscript,chapter,data


@pytest.mark.parametrize('door',['native','http'])
def test_real_unplaced_visual_full_reader_completion_then_placement_is_stable(tmp_path,door):
    from laplace.pipeline import visual_production as vp
    from laplace.web import project_work_surface
    parent,stage,manuscript,chapter,data=_visual_improvement_fixture(tmp_path)
    assert not vp.load(manuscript)['specs'][0].get('section')
    assert '\\begin{figure}' not in chapter.read_text() and 'First body' not in chapter.read_text()
    raw=_refresh_typed_stage(tmp_path,parent,stage)
    tasks=project_work._tasks('book',tmp_path)
    assert raw['manuscript_stage']['cut']['reader_readiness']['status']=='READY'
    assert prepared_work.stage_currentness(raw,tasks,tmp_path,require_qualified=True)['status']=='CURRENT'
    detail=project_work.read('book',{'view':'detail','id':stage['id']},tmp_path)
    payload={**detail['allowed_actions']['task_status']['payload'],'status':'done','evidence':['typed-stage-output.txt']}
    if door=='native':
        writing_tools.execute(tmp_path,'book','work','task_status',payload)
    else:
        code,_,body=project_work_surface.handle('/work/transition',{},'POST',
            json.dumps({'project':'book',**payload}).encode(),repo_root=tmp_path)
        assert code==200,body
    assert project_work.read('book',{'view':'detail','id':stage['id']},tmp_path)['task']['readiness']['satisfies_prerequisites']
    original=[s['reader_basis'] for s in _reader_visual_subjects(tmp_path)]
    writing_tools.execute(tmp_path,'book','work','visual_place',{'id':'reader-plot',
        'file':chapter.relative_to(tmp_path).as_posix(),'after_line':1})
    chapter.write_text(chapter.read_text()+'\nLater prose explains this previously planned drawing.\n')
    assert [s['reader_basis'] for s in _reader_visual_subjects(tmp_path)]==original
    assert project_work.read('book',{'view':'detail','id':stage['id']},tmp_path)['task']['readiness']['satisfies_prerequisites']
    for route,query in [('/work/structure',{'project':['book'],'view':['detail'],'section_ids':['first']}),
                        ('/work/state',{'project':['book'],'view':['detail'],'id':[stage['id']]}),
                        ('/work/pipeline',{'project':['book']})]:
        code,_,body=project_work_surface.handle(route,query,'GET',repo_root=tmp_path)
        assert code==200,body
        seen=json.loads(body)
        if route=='/work/structure':
            assert all(not s['diagnostics'] and s['input_currentness']['status']=='CURRENT'
                for s in [seen['sections'][0]['reader_transition'],*seen['sections'][0]['paragraph_plan']['paragraphs']['items']])
        elif route=='/work/state':assert seen['task']['readiness']['satisfies_prerequisites']


@pytest.mark.parametrize('damage',['data','output','caption','citation'])
def test_real_visual_change_reopens_completed_work_and_both_admission_doors(tmp_path,monkeypatch,damage):
    from laplace.pipeline import visual_production as vp
    from laplace.web import project_work_surface,authoring as controller
    from laplace.core import checkout
    parent,stage,manuscript,chapter,data=_visual_improvement_fixture(tmp_path)
    if damage=='citation':
        main=manuscript/'Fixture-Book.tex'
        main.write_text(main.read_text()+'\n\\bibliography{visual-reader}\n')
        bib=manuscript/'visual-reader.bib'
        bib.write_text('@article{VisualReader, title={A real readable fixture entry}}\n')
        row=_reader_visual_subjects(tmp_path)[1]
        writing_tools.execute(tmp_path,'book','work','structure_change',{
            **row['edit_action']['payload'],'changes':{'citations':['VisualReader']}})
        _observe_reader_visual_subjects(tmp_path)
    _refresh_typed_stage(tmp_path,parent,stage)
    _native_done(tmp_path,'book',stage['id'],['typed-stage-output.txt'])
    draft=_stage_from_route(tmp_path,'book',parent)
    row=_reader_visual_subjects(tmp_path)[1]
    old_action=row['edit_action']
    if damage=='data':data.write_text('x,y\n0,1\n1,9\n')
    elif damage=='output':
        output=manuscript/vp.load(manuscript)['specs'][0]['render']['outputs'][0]
        output.write_bytes(output.read_bytes()+b'\nchanged drawing output')
    elif damage=='caption':
        spec=vp.load(manuscript)['specs'][0]
        writing_tools.execute(tmp_path,'book','work','visual_create',{'spec':{
            'id':'reader-plot','caption':'Changed reader-relevant caption.'},'expected_revision':vp.digest(spec)})
    else:bib.write_text(bib.read_text().replace('real readable','changed readable'))
    current=project_work.read('book',{'view':'detail','id':stage['id']},tmp_path)
    assert current['task']['currentness']['status']!='CURRENT'
    assert not current['task']['readiness']['satisfies_prerequisites']
    for door in ['native','http']:
        payload={**current['allowed_actions']['task_status']['payload'],'status':'done','evidence':['typed-stage-output.txt']}
        if door=='native':
            with pytest.raises(ValueError):
                writing_tools.execute(tmp_path,'book','work','task_status',payload)
        else:
            code,_,body=project_work_surface.handle('/work/transition',{},'POST',
                json.dumps({'project':'book',**payload}).encode(),repo_root=tmp_path)
            assert code>=400,body
    monkeypatch.setattr(turn_admission,'new_session',lambda *a,**kw:pytest.fail('session effect'))
    monkeypatch.setattr(writing_provider,'WritingTurn',lambda *a,**kw:pytest.fail('provider effect'))
    monkeypatch.setattr(checkout,'repo_root',lambda:tmp_path)
    downstream=project_work.read('book',{'view':'detail','id':draft['id']},tmp_path)['task']
    request={'project':'book','work_id':draft['id'],'session_id':'WS-original','mode':'work','text':'Do the exact draft.',
        'expected_work_scope_revision':downstream['work_scope_revision'],
        'expected_dependency_revision':downstream['dependency_revision']}
    with pytest.raises(project_work.WorkConflict):
        turn_admission.start_turn(tmp_path,request)
    code,_,body=controller.handle('/authoring/turn',{},'POST',json.dumps(request).encode())
    assert code==409,body
    # Scientific recovery is deliberate: old guards refuse, current exact
    # observations and normal stage re-preparation do not renew old acceptance.
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        writing_tools.execute(tmp_path,'book','work','structure_change',{
            **old_action['payload'],'changes':{},'input_observations':old_action['payload']['expected_reader_basis']['inputs']})
    if damage!='citation':writing_tools.execute(tmp_path,'book','work','visual_render',{'id':'reader-plot'})
    _observe_reader_visual_subjects(tmp_path)
    _refresh_typed_stage(tmp_path,parent,stage)
    current=project_work.read('book',{'view':'detail','id':stage['id']},tmp_path)
    writing_tools.execute(tmp_path,'book','work','task_status',{
        **current['allowed_actions']['task_status']['payload'],'status':'in-progress'})
    _native_done(tmp_path,'book',stage['id'],['typed-stage-output.txt'])
    assert project_work.read('book',{'view':'detail','id':stage['id']},tmp_path)['task']['readiness']['satisfies_prerequisites']
    assert sum(r.get('record')=='project-work' and r.get('id')==stage['id'] for r in project_work._rows(tmp_path))>=2


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES', str(tmp_path / 'workspaces'))
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()
    yield
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()
    shutil.rmtree(tmp_path, ignore_errors=True)


def prepare(root):
    action = _prepare_action(root)
    return writing_tools.execute(root, 'book', 'work', action['operation'], action['payload'])



def _prepare_action(root, index=0):
    # G18: list rows carry one detail handle; the prepare action is on the section's detail read
    listed = project_structure.read('book', {'view': 'summary'}, root)['sections']['items'][index]
    return project_structure.read('book', listed['detail_read']['payload'], root)['sections'][0]['prepare_action']

def test_prepare_reuses_exact_cut_and_keeps_source_and_histories_unchanged(tmp_path, monkeypatch):
    manuscript, source, _ = _section_fixture(tmp_path)
    before = source.read_bytes()
    monkeypatch.setattr(writing_provider, 'WritingTurn', lambda *a, **k: pytest.fail('provider started'))
    first = prepare(tmp_path)
    journal = (tmp_path / records_fold._STORE).read_bytes()
    ledger = project_work._ledger(tmp_path).read_bytes()
    action = _prepare_action(tmp_path)
    second = prepared_work.prepare('book', action['payload'], tmp_path)
    assert first['work_id'] == second['work_id']
    assert second['reused'] and not second['changed'] and not second['provider_started']
    assert (tmp_path / records_fold._STORE).read_bytes() == journal
    assert project_work._ledger(tmp_path).read_bytes() == ledger
    assert source.read_bytes() == before
    assert first['preparation']['current']
    assert first['artifact']['id'].startswith('ART-')
    assert first['run_action']['payload']['expected_work_scope_revision'] == first['task']['work_scope_revision']
    assert records.fold_records(tmp_path)['sessions'] == {}
    assert records.fold_records(tmp_path)['turns'] == {}


@pytest.mark.parametrize('change', ['source', 'plan', 'reader'])
def test_changed_prepared_inputs_refuse_run_before_session_effect(tmp_path, monkeypatch, change):
    manuscript, source, _ = _section_fixture(tmp_path)
    receipt = prepare(tmp_path)
    if change == 'source':
        source.write_text(source.read_text() + '% concurrent source edit\n')
    elif change == 'plan':
        path = manuscript / 'projection_plan.json'
        plan = json.loads(path.read_text())
        plan['sections'][0]['job'] = 'Changed intention'
        path.write_text(json.dumps(plan))
    else:
        current=project_structure.read('book',{'view':'detail','section_ids':['first']},tmp_path)['sections'][0]
        writing_tools.execute(tmp_path,'book','work','structure_change',{
            **current['reader_transition']['edit_action']['payload'],'changes':{'entry_state':'Changed input'}})
    monkeypatch.setattr(turn_admission, 'new_session', lambda *a, **k: pytest.fail('session effect'))
    with pytest.raises(project_work.WorkConflict) as refusal:
        turn_admission.start_turn(tmp_path, receipt['run_action']['payload'])
    assert not refusal.value.details['preparation']['current']
    retained = project_work.read('book', {'view': 'detail', 'id': receipt['work_id']}, tmp_path)
    assert retained['task']['preparation']['status'] == 'STALE'
    assert retained['task']['recorded_status'] == 'open'


def test_old_plan_observation_cannot_prepare_new_cut(tmp_path):
    manuscript, _, _ = _section_fixture(tmp_path)
    action = _prepare_action(tmp_path)
    path = manuscript / 'projection_plan.json'
    path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        project_structure.change('book', action['payload'], tmp_path)
    assert not project_work._tasks('book', tmp_path)


def test_prepared_run_rejects_child_and_review_roles(tmp_path):
    _section_fixture(tmp_path)
    receipt = prepare(tmp_path)
    task = project_work._tasks('book', tmp_path)[receipt['work_id']]
    for context in [{'mode': 'review'}, {'mode': 'work', 'session': {'role': 'review'}},
                    {'mode': 'work', 'session': {'role': 'author', 'dispatch_id': 'child'}}]:
        with pytest.raises(ValueError, match='deliberate author parent'):
            prepared_work.require_current('book', tmp_path, task, **context)


def test_absent_optional_preparation_preserves_old_work_identity():
    old = {'id': 'legacy', 'title': 'Keep accepted receipt', 'goal': 'Same work'}
    assert project_work._task_revision(old) == project_work._task_revision({**old, 'prepared_storyboard': None})


def test_generic_native_and_http_preparation_share_one_owner(tmp_path):
    from laplace.native import verbs as writing_verbs
    from laplace.web import project_work_surface
    _section_fixture(tmp_path)
    action = _prepare_action(tmp_path)
    route, request = writing_verbs.from_owner_call('structure_change', action['payload'], project='book', root=tmp_path)
    assert (route.verb, route.concept) == ('create', 'task@project')
    native = writing_tools.request(tmp_path, 'book', 'work', request)['owner_response']
    code, _, raw = project_work_surface.handle('/work/structure/change', {}, 'POST',
        json.dumps({'project':'book', **action['payload']}).encode(), tmp_path)
    http = json.loads(raw)
    assert code == 200
    assert http['work_id'] == native['work_id']
    assert http['artifact'] == native['artifact']
    assert http['run_action'] == native['run_action']


def test_retained_artifact_failure_has_exact_recovery_and_same_cut_reuses_it(tmp_path, monkeypatch):
    from laplace.web import project_work_surface
    _, source, _ = _section_fixture(tmp_path)
    before = source.read_bytes()
    action = _prepare_action(tmp_path)
    with monkeypatch.context() as patch:
        def fail_work(*args, **kwargs):
            raise OSError('fixture Work publication unavailable')
        patch.setattr(project_work, 'task', fail_work)
        code, _, raw = project_work_surface.handle('/work/structure/change', {}, 'POST',
            json.dumps({'project':'book', **action['payload']}).encode(), tmp_path)
    failure = json.loads(raw)
    assert code == 422
    stage = failure['preparation_publication']
    assert stage['state'] == 'ARTIFACT_RETAINED' and stage['work_publication'] == 'UNCONFIRMED'
    assert not stage['complete'] and 'source_effect' not in failure
    assert stage['artifact']['human_read']['artifact_id'] == stage['artifact']['id']
    assert failure['next_reads'][0]['http'] == stage['artifact']['human_read']['http']
    assert not project_work._tasks('book', tmp_path)
    recovered = prepared_work.prepare('book', action['payload'], tmp_path)
    assert recovered['artifact']['id'] == stage['artifact']['id']
    assert recovered['work_id'] == stage['work_id']
    assert len([row for row in records.index(tmp_path).by_project['book']
                if row.get('record') == 'writing-artifact']) == 1
    assert source.read_bytes() == before


def test_preparation_uses_actual_m2_reader_checks_and_normalized_source_pins(tmp_path):
    from laplace.projects import artifacts
    _section_fixture(tmp_path)
    for proposition in ['First planned gain','Second planned gain']:
        selected=project_structure.read('book',{'view':'detail','section_ids':['first']},tmp_path)['sections'][0]
        action=selected['paragraph_plan']['create_action']
        writing_tools.execute(tmp_path,'book','work','structure_change',{
            **action['payload'],'changes':{'proposition':proposition}})
    current=project_structure.read('book',{'view':'detail','section_ids':['first']},tmp_path)['sections'][0]
    receipt=prepare(tmp_path)
    value=json.loads(artifacts.read(tmp_path,'book',{'id':receipt['artifact']['id'],'limit':40000})['content'])
    assert 'narrative_checks' not in value
    check=value['reader_checks'][0]
    assert check['paragraph_count']==2
    assert [row['input_currentness'] for row in check['paragraphs']]==[
        row['input_currentness'] for row in current['paragraph_plan']['paragraphs']['items']]
    assert 'not review' in check['qualification']
    assert all(pin is None or re.fullmatch(r'sha256:[0-9a-f]{64}',pin)
        for pin in value['basis']['input_revisions'].values())


def test_old_preparation_contract_remains_retained_and_requires_explicit_reprepare(tmp_path):
    from laplace.projects import artifacts
    _section_fixture(tmp_path)
    receipt=prepare(tmp_path)
    value=json.loads(artifacts.read(tmp_path,'book',{'id':receipt['artifact']['id'],'limit':40000})['content'])
    value['basis'].pop('preparation_contract')
    saved=artifacts.store(tmp_path,'book',{'path':'development/legacy-prepared.json','before':None,
        'content':json.dumps(value),'reason':'Retained old preparation fixture.'})
    before=(tmp_path/saved['path']).read_bytes()
    observed=prepared_work.observe('book',tmp_path,{'artifact_id':saved['id'],'revision':saved['revision']})
    assert not observed['current'] and observed['status']=='STALE'
    assert (tmp_path/saved['path']).read_bytes()==before


def test_prepared_completion_requires_actual_reviewed_dispatch_prerequisite(tmp_path, monkeypatch):
    from laplace.writing import provider as writing_provider
    from test_writing_dispatch import CATALOGUE, _plan
    from work_read_helpers import guarded_transition
    _section_fixture(tmp_path)
    receipt = prepare(tmp_path)
    ident = receipt['work_id']
    with pytest.raises(ValueError, match='actual contained dispatch'):
        guarded_transition('book', {'id': ident, 'status': 'done',
                                    'evidence': receipt['task']['evidence']}, tmp_path)
    monkeypatch.setattr(writing_provider, 'capabilities', lambda *a, **k: CATALOGUE)
    monkeypatch.setattr(writing_provider, 'capabilities', lambda *a, **k: CATALOGUE)
    monkeypatch.setattr(writing_provider, 'WritingTurn', lambda *a, **k: pytest.fail('provider started'))
    records.bank(tmp_path, {'record': 'writing-session', 'id': 'parent', 'project': 'book',
                                      'provider': 'claude', 'role': 'author'})
    records.bank(tmp_path, {'record': 'writing-turn', 'id': 'parent-turn', 'session_id': 'parent',
                                      'project': 'book', 'mode': 'work', 'work_id': ident, 'text': 'Execute the inspected cut.'})
    planned = writing_tools.execute(tmp_path, 'book', 'work', 'dispatch_plan', {
        'title': 'Prepared execution', 'goal': 'Return reviewed scoped results',
        'path': 'development/execution-plan.json', 'plan': _plan(tmp_path)}, turn_id='parent-turn')
    tasks = project_work._tasks('book', tmp_path)
    assert tasks[planned['dispatch_id']]['parent_work_id'] == ident
    assert tasks[ident]['depends_on'] == [planned['dispatch_id']]
    assert planned['parent_work_read']['payload']['id'] == ident
    assert project_work.read('book', {'view': 'detail', 'id': ident}, tmp_path)['task']['status'] == 'blocked'
    with pytest.raises(ValueError, match='blocked task cannot complete'):
        guarded_transition('book', {'id': ident, 'status': 'done',
                                    'evidence': receipt['task']['evidence']}, tmp_path)


def test_durable_run_action_resumes_exact_parent_and_rejects_duplicate_owner(tmp_path, monkeypatch):
    _section_fixture(tmp_path)
    receipt = prepare(tmp_path)
    ident = receipt['work_id']
    records.bank(tmp_path, {'record': 'writing-turn', 'id': 'retained-turn',
        'project': 'book', 'session_id': 'WS-retained', 'work_id': ident, 'mode': 'work', 'text': 'Original execution.'})
    task = project_work.read('book', {'view': 'detail', 'id': ident}, tmp_path)['task']
    assert task['run_action']['label'] == 'Resume recorded parent'
    assert task['run_action']['payload']['session_id'] == 'WS-retained'
    assert task['prepared_execution']['items'][0]['state'] == 'UNCONFIRMED'
    with pytest.raises(project_work.WorkConflict, match='different new conversation'):
        prepared_work.require_current('book', tmp_path, task, mode='work')
    prepared_work.require_current('book', tmp_path, task, mode='work', session={'id': 'WS-retained', 'role': 'author'})
    monkeypatch.setattr(session_reads, 'child_execution', lambda *a, **k: {
        'turn_id': 'retained-turn', 'state': 'ORPHANED'})
    monkeypatch.setattr(child_hosts, "child_execution", session_reads.child_execution)   # the owner the family calls directly
    blocked = project_work.read('book', {'view': 'detail', 'id': ident}, tmp_path)['task']
    assert not blocked['run_action']['permitted']
    with pytest.raises(project_work.WorkConflict, match='running parent'):
        prepared_work.require_current('book', tmp_path, task, mode='work', session={'id': 'WS-retained', 'role': 'author'})


@pytest.mark.parametrize('disposition', ['withdrawn', 'cancelled'])
def test_disposed_failed_attempt_does_not_block_successor_execution_join(tmp_path, disposition):
    from work_read_helpers import guarded_transition
    _section_fixture(tmp_path)
    receipt = prepare(tmp_path)
    parent = receipt['work_id']
    old = project_work.task('book', {'title':'Old attempt', 'goal':'Retained failed execution',
        'kind':'dispatch', 'parent_work_id':parent}, tmp_path)
    guarded_transition('book', {'id':old['id'], 'status':disposition,
        'summary':'Explicitly abandon this failed attempt and retain its history.'}, tmp_path)
    successor = project_work.task('book', {'title':'Successor', 'goal':'Return independently reviewed results',
        'kind':'dispatch', 'parent_work_id':parent}, tmp_path)
    prior = project_work._tasks('book', tmp_path)[parent]
    project_work.task('book', {'id':parent, 'depends_on':[successor['id']],
        'expected_work_revision':project_work._task_revision(prior)}, tmp_path)
    # The retired child no longer makes the join impossible. Completion still
    # refuses because the successor has no accepted current return/review proof.
    with pytest.raises(ValueError, match='blocked task cannot complete'):
        guarded_transition('book', {'id':parent, 'status':'done',
            'evidence':receipt['task']['evidence']}, tmp_path)
    assert project_work._tasks('book', tmp_path)[old['id']]['parent_work_id'] == parent


def test_changed_inputs_prepare_a_distinguishable_attempt_not_a_twin_row(tmp_path, monkeypatch):
    # G10: the same sections prepared again on changed inputs are new Work with a title that
    # says so; the earlier attempt keeps its own id and title. An unchanged cut still reuses.
    manuscript, source, _ = _section_fixture(tmp_path)
    monkeypatch.setattr(writing_provider, 'WritingTurn', lambda *a, **k: pytest.fail('provider started'))
    first = prepare(tmp_path)
    path = manuscript / 'projection_plan.json'
    plan = json.loads(path.read_text())
    plan['sections'][0]['job'] = 'Changed intention'
    path.write_text(json.dumps(plan))
    second = prepare(tmp_path)
    assert second['work_id'] != first['work_id'] and not second['reused']
    titles = {row['id']: row['title'] for row in project_work.read('book', {'view': 'summary'}, tmp_path)['tasks']}
    assert titles[first['work_id']] == first['task']['title'] and not titles[first['work_id']].endswith('attempt 2')
    assert titles[second['work_id']].endswith(' · attempt 2') and titles[second['work_id']].startswith('Develop reader plan: ')
    assert len(set(titles.values())) == len(titles)


def _ordinary_programme(root):
    from laplace.writing import stages
    from laplace.research import concepts, literature_support
    state = concepts.state("book", root=root)
    if "concept:first" not in literature_support.network("book", root).get("nodes", {}):
        # The old fixture plan named an absent concept. Use an actual authored
        # definition through the canonical owner, not an invented result record.
        writing_tools.execute(root, "book", "work", "concept_change", {
            "operation": "add_node", "node": "concept:first", "node_kind": "definition",
            "essence": "An explicitly authored fixture definition.", "base_revision": state["revision"]})
    action = prepared_work.programme_create_action("book", root)
    action["payload"]["section_ids"] = ["first"]
    parent = writing_tools.execute(root, "book", "work", action["operation"], action["payload"])
    records.bank(root, {"record": "writing-session", "id": "WS-original", "project": "book",
                        "provider": "codex", "role": "author"})
    records.bank(root, {"record": "writing-turn", "id": "WT-programme", "project": "book",
                        "session_id": "WS-original", "work_id": parent["id"], "mode": "work"})
    records.bank(root, {"record": "writing-reply", "id": "WR-programme", "project": "book",
                        "session_id": "WS-original", "turn_id": "WT-programme", "status": "completed"})
    return parent


def _execute_route_action(root, action):
    return writing_tools.execute(root, "book", "work", action["operation"], action["payload"])


def test_real_ordinary_stage_work_join_and_parent_actions_without_provider_or_source_effect(tmp_path, monkeypatch):
    from work_read_helpers import guarded_transition
    manuscript, source, _ = _section_fixture(tmp_path)
    before = source.read_bytes()
    monkeypatch.setattr(writing_provider, "WritingTurn", lambda *a, **k: pytest.fail("provider started"))
    parent = _ordinary_programme(tmp_path)
    route = prepared_work.programme_route("book", tmp_path, parent["id"])
    assert not route["issues"] and route["next_action"]["operation"] == "task"
    projected = writing_tools.execute(tmp_path, "book", "work", "pipeline", {})["programme"]
    assert projected["routes"][0]["work_id"] == parent["id"]
    assert projected["routes"][0]["next_action"] == route["next_action"]
    results = _execute_route_action(tmp_path, route["next_action"])
    route = prepared_work.programme_route("book", tmp_path, parent["id"])
    assert route["join_action"] and not route["next_action"]["permitted"]
    _execute_route_action(tmp_path, route["join_action"])
    route = prepared_work.programme_route("book", tmp_path, parent["id"])
    run = route["next_action"]
    assert run["permitted"]
    assert run["http"]["route"] == "/authoring/turn"
    assert run["payload"]["session_id"] == "WS-original"
    assert run["payload"]["work_id"] == results["id"]
    assert run["payload"]["expected_work_scope_revision"]
    # Preparation has emitted only ordinary owner actions, not a model launch.
    evidence = tmp_path / "results-evidence.txt"
    evidence.write_text("Fixture scoped result interpretation, not scientific acceptance.")
    guarded_transition("book", {"id": results["id"], "status": "done",
                                "evidence": ["results-evidence.txt"]}, tmp_path)
    support_action = prepared_work.programme_route("book", tmp_path, parent["id"])["next_action"]
    assert support_action["payload"]["kind"] == "writing-literature-support"
    support = _execute_route_action(tmp_path, support_action)
    assert support["depends_on"] == [results["id"]]
    assert support["parent_work_id"] == parent["id"]
    assert source.read_bytes() == before
    assert records.fold_records(tmp_path)["sessions"].keys() == {"WS-original"}


def test_support_work_does_not_wait_on_late_acquisition_citation_build_completion(tmp_path):
    from work_read_helpers import guarded_transition
    _section_fixture(tmp_path)
    parent = _ordinary_programme(tmp_path)
    result = _execute_route_action(tmp_path, prepared_work.programme_route("book", tmp_path, parent["id"])["next_action"])
    (tmp_path / "basis.txt").write_text("Fixture current scoped handoff.")
    guarded_transition("book", {"id": result["id"], "status": "done", "evidence": ["basis.txt"]}, tmp_path)
    support = _execute_route_action(tmp_path, prepared_work.programme_route("book", tmp_path, parent["id"])["next_action"])
    acquisition = project_work.task("book", {"title": "Acquire exact passage", "goal": "Cite and build later",
        "kind": "literature-acquisition", "parent_work_id": parent["id"]}, tmp_path)
    guarded_transition("book", {"id": support["id"], "status": "done", "evidence": ["basis.txt"]}, tmp_path)
    route = prepared_work.programme_route("book", tmp_path, parent["id"])
    improvement = _execute_route_action(tmp_path, route["next_action"])
    assert improvement["depends_on"] == [support["id"]]
    assert acquisition["id"] not in improvement["depends_on"]
    assert acquisition["id"] in route["join_action"]["payload"]["depends_on"]
    assert parent["id"] not in improvement["depends_on"]


def test_changed_predecessor_or_unknown_busy_parent_exposes_recovery_not_duplicate_job(tmp_path):
    _section_fixture(tmp_path)
    parent = _ordinary_programme(tmp_path)
    results = _execute_route_action(tmp_path, prepared_work.programme_route("book", tmp_path, parent["id"])["next_action"])
    route = prepared_work.programme_route("book", tmp_path, parent["id"],
                                         origin_parent_session_id="WS-replacement")
    assert route["issues"] and not route["next_action"]["permitted"]
    assert route["original_parent_session_id"] == "WS-original"
    records.bank(tmp_path, {"record": "writing-turn", "id": "WT-uncertain", "project": "book",
        "session_id": "WS-original", "work_id": results["id"], "mode": "work"})
    route = prepared_work.programme_route("book", tmp_path, parent["id"])
    assert route["unresolved_execution"] and not route["next_action"]["permitted"]
    assert "Never replay children" in route["recovery"]


def test_prepared_support_receipts_are_separate_from_bibtex_and_detect_changed_passage(tmp_path, monkeypatch):
    from laplace.research import literature_support
    _section_fixture(tmp_path)
    monkeypatch.setattr(literature_support, "network", lambda *a: {
        "nodes": {"concept:first": {"kind": "result"}}, "relations": []})
    support = {"node": "concept:first", "meaning_revision": "claim-pin", "qualification": "AUTHORED_BASIS",
               "sources": [{"source_id": "citation:source", "qualification": "PASSAGE_OBSERVED",
                            "reading_receipt": {"source_sha256": "passage-v1"}}], "gaps": []}
    monkeypatch.setattr(literature_support, "for_node", lambda *a, **k: support)
    receipt = prepare(tmp_path)
    binding = {"artifact_id": receipt["artifact"]["id"], "revision": receipt["artifact"]["revision"]}
    old = prepared_work.observe("book", tmp_path, binding)
    assert old["current"] and old["basis"]["literature_support"]["nodes"]
    assert old["basis"]["reader_input_bases"] == old["observed_basis"]["reader_input_bases"]
    support["sources"][0]["reading_receipt"]["source_sha256"] = "passage-v2"
    changed = prepared_work.observe("book", tmp_path, binding)
    assert not changed["current"]
    assert changed["basis"]["input_revisions"] == changed["observed_basis"]["input_revisions"]
    assert changed["basis"]["literature_support"] != changed["observed_basis"]["literature_support"]


def test_judgement_stage_is_review_managed_not_a_producer_self_score(tmp_path):
    from laplace.writing import stages
    recipe = stages.programme(tmp_path)
    judge = next(phase for phase in recipe["phases"] if phase["id"] == "judgement")
    _section_fixture(tmp_path)
    parent = _ordinary_programme(tmp_path)
    owned = project_work.task("book", {"title": judge["title"], "goal": judge["completion"],
        "kind": judge["work_kind"], "parent_work_id": parent["id"],
        "review_obligations": judge["review_obligations"]}, tmp_path)
    detail = project_work.read("book", {"view": "detail", "id": owned["id"]}, tmp_path)
    assert detail["task"]["review"]["remaining"] == ["reader-sensitive"]
    assert "done" in detail["allowed_actions"]["task_status"]["refused"]


def _native_done(root, project, ident, evidence):
    detail = project_work.read(project, {"view": "detail", "id": ident}, root)
    return writing_tools.execute(root, project, "work", "task_status", {
        **detail["allowed_actions"]["task_status"]["payload"],
        "status": "done", "evidence": evidence})


def _stage_from_route(root, project, parent):
    route = prepared_work.programme_route(project, root, parent["id"])
    if route["join_action"]:
        writing_tools.execute(root, project, "work", "task", route["join_action"]["payload"])
        route = prepared_work.programme_route(project, root, parent["id"])
    action = route["next_action"]
    assert action and action.get("operation") == "task", route
    return writing_tools.execute(root, project, "work", "task", action["payload"])


@pytest.mark.parametrize("door", ["native", "http"])
@pytest.mark.parametrize("external", [False, True])
def test_zero_partial_full_terminal_route_and_stale_acceptance_use_real_work_owners(tmp_path, monkeypatch, door, external):
    """Actual Work/review/export owners, with synthetic compiler output receipts
    at the external TeX boundary. No live provider, TeX or scientific result."""
    from laplace.web import project_work_surface
    from laplace.manuscript import manuscript_source, document_style, projection_viewer as pv, tex_dependencies
    from laplace.core.records import journal
    _section_fixture(tmp_path)
    parent = _ordinary_programme(tmp_path)
    if external:
        from laplace.research import literature_support
        original = tmp_path / "terminal-external-source.txt"
        original.write_text("The fixture definition is used only within its explicit conditions.\n")
        imported = writing_tools.execute(tmp_path, "book", "work", "literature_import", {
            "metadata": {"title": "Terminal source fixture", "creators": ["Fixture Author"],
                         "year": "2026", "item_type": "unpublished"},
            "provenance": {"description": "Disposable terminal qualification source", "path": str(original)},
            "citekey": "ScopeFixture"})
        key = imported["association"]["key"]
        read = writing_tools.execute(tmp_path, "book", "work", "reference_text", {"key": key, "limit": 1000})
        writing_tools.execute(tmp_path, "book", "work", "literature_bind", {
            "key": key, "claim_id": "concept:first",
            "claim_revision": literature_support.meaning_revision("book", "concept:first", tmp_path),
            "relation": "supports", "rationale": "Fixture support for this explicit limited statement.",
            "reading_status": "partial", "reading_id": read["reading_receipt"]["id"],
            "evidence": {"locator": read["reading_receipt"]["locator"], "excerpt": "within its explicit conditions"}})
    (tmp_path / "terminal-evidence.txt").write_text("Fixture stage interpretation.")
    evidence = ["terminal-evidence.txt"]

    def done(ident, paths=evidence):
        detail = project_work.read("book", {"view": "detail", "id": ident}, tmp_path)
        payload = {**detail["allowed_actions"]["task_status"]["payload"], "status": "done", "evidence": paths}
        if door == "native":
            return writing_tools.execute(tmp_path, "book", "work", "task_status", payload)
        code, _, raw = project_work_surface.handle("/work/transition", {}, "POST",
            json.dumps({"project": "book", **payload}).encode(), tmp_path)
        if code >= 400:
            raise ValueError(json.loads(raw).get("error") or raw.decode())
        return json.loads(raw)

    contract = project_work._tasks("book", tmp_path)[parent["id"]]["manuscript_programme"]
    required = contract["required_stages"]
    assert len(required) == len(set(required.values())) == 7
    with pytest.raises(ValueError):
        done(parent["id"])                    # zero required stages, arbitrary evidence
    made = {}
    for phase in ["results", "literature", "improvement", "draft", "judgement"]:
        if phase == "improvement":
            _author_typed_reader_plan(tmp_path)
        child = _stage_from_route(tmp_path, "book", parent)
        assert child["id"] == required[phase]
        made[phase] = child
        if phase == "judgement":
            break
        done(child["id"])
        with pytest.raises(ValueError):
            done(parent["id"])                # every proper partial prefix refuses

    judge = made["judgement"]
    with pytest.raises(ValueError):
        done(judge["id"])                     # producer artifact cannot substitute independent review
    for turn, session, stage_id, role in [
        ("WT-reader-handoff", "WS-original", judge["id"], "author"),
        ("WT-independent-reader", "WS-independent", judge["id"], "review")]:
        if session != "WS-original":
            records.bank(tmp_path, {"record": "writing-session", "id": session, "project": "book",
                                    "provider": "codex", "model": "fixture", "role": role})
        records.bank(tmp_path, {"record": "writing-turn", "id": turn, "session_id": session,
            "project": "book", "work_id": stage_id, "mode": "review" if role == "review" else "work"})
        records.bank(tmp_path, {"record": "writing-reply", "id": "WR-" + turn, "turn_id": turn,
                                "session_id": session, "project": "book", "status": "completed"})
    guard = project_work._task_revision(project_work._tasks("book", tmp_path)[judge["id"]])
    import hashlib
    pin = "sha256:" + hashlib.sha256((tmp_path / evidence[0]).read_bytes()).hexdigest()
    handoff = writing_tools.execute(tmp_path, "book", "work", "work_review", {
        "id": judge["id"], "phase": "handoff", "request_id": "terminal-reader-handoff",
        "expected_work_revision": guard, "pins": {evidence[0]: pin}}, "WT-reader-handoff")
    accepted = writing_tools.execute(tmp_path, "book", "review", "work_review", {
        "id": judge["id"], "phase": "review", "request_id": "terminal-reader-accept",
        "expected_work_revision": guard, "handoff_id": handoff["phase"]["id"],
        "obligation_id": "reader-sensitive", "verdict": "ACCEPT"}, "WT-independent-reader")
    assert accepted["phase"]["independence"] == "INDEPENDENT"
    done(judge["id"])
    synthesis = _stage_from_route(tmp_path, "book", parent)
    done(synthesis["id"])
    exported = _stage_from_route(tmp_path, "book", parent)
    done(exported["id"])
    route = prepared_work.programme_route("book", tmp_path, parent["id"])
    if route["join_action"]:
        writing_tools.execute(tmp_path, "book", "work", "task", route["join_action"]["payload"])
    with pytest.raises(ValueError, match="synthesis"):
        done(parent["id"])                    # all seven Done still lacks actual parent synthesis/export

    records.bank(tmp_path, {"record": "writing-turn", "id": "WT-terminal-synthesis", "project": "book",
        "session_id": "WS-original", "work_id": synthesis["id"], "mode": "work"})
    writing_tools.execute(tmp_path, "book", "work", "work_review", {
        "id": judge["id"], "phase": "synthesis", "request_id": "terminal-parent-synthesis",
        "expected_work_revision": guard, "consumes": [handoff["phase"]["id"], accepted["phase"]["id"]],
        "summary": "Fixture parent consumes exact accepted reader judgement."}, "WT-terminal-synthesis")
    with pytest.raises(ValueError, match="export|build"):
        done(parent["id"])                    # synthesis is not an export/build

    source = manuscript_source.resolve("book", repo_root=tmp_path)
    tex = tmp_path / source["root"]
    tex.with_suffix(".pdf").write_bytes(b"%PDF-synthetic-compiler-boundary-fixture")
    tex.with_suffix(".synctex.gz").write_bytes(b"Synthetic compiler-boundary SyncTeX fixture")
    tex.with_suffix(".aux").write_text("")
    tex.with_suffix(".bbl").write_text("")
    pv._write_recompile_status(tex, {"state": "done", "ok": True, "finished": 123,
        "dependencies": tex_dependencies.snapshot(tex, tmp_path),
        "outputs": pv._build_output_snapshot(tex, tmp_path),
        "pdf": tex.with_suffix(".pdf").relative_to(tmp_path).as_posix(), "built_ts": 123})
    actual_export = document_style.export_pdf("book", tmp_path)
    # Real export owner wrote and validated the PDF/receipt and journal event.
    done(exported["id"], [*evidence, actual_export["file"], actual_export["receipt"]])
    if not external:
        acquisition = project_work.task("book", {"title": "Definition support closure", "goal": "Observe the scoped definition",
            "kind": "literature-acquisition", "parent_work_id": parent["id"],
            "logical_target": {"kind": "node", "node_id": "concept:first"}}, tmp_path)
        with pytest.raises(ValueError):
            done(parent["id"])                    # late required acquisition cannot disappear from terminal join
        route = prepared_work.programme_route("book", tmp_path, parent["id"])
        writing_tools.execute(tmp_path, "book", "work", "task", route["join_action"]["payload"])
        with pytest.raises(ValueError):
            done(parent["id"])
        from laplace.research import literature_support
        assert literature_support.scope("book", tmp_path, task_id=acquisition["id"])["ready_for_completion"]
        done(acquisition["id"])
    else:
        # All seven stage Works, independent judgement, original-parent synthesis
        # and current export exist, but NO acquisition child can trigger the old gate.
        assert not any(row.get("task_kind") == "literature-acquisition"
                       for row in project_work._tasks("book", tmp_path).values())
        coverage = literature_support.scope("book", tmp_path, node="concept:first")
        assert {"not-yet-cited", "citation-not-rendered"}.issubset({g["kind"] for g in coverage["gaps"]})
        with pytest.raises(ValueError, match="Final scoped literature"):
            done(parent["id"])

        file = "chapters/chapter-01.tex"
        from laplace.pipeline import authoring
        selection = {"files": [file], "line_start": 2, "line_end": 2}
        context = authoring.build_context("book", selection, repo_root=tmp_path)
        records.bank(tmp_path, {"record": "writing-turn", "id": "WT-terminal-citation",
            "session_id": "WS-original", "project": "book", "work_id": required["draft"],
            "mode": "work", "selection": selection, "context_id": context["context_id"],
            "dependencies": context["dependencies"], "document": context["document"],
            "text": "Fixture-authorised guarded citation application."})
        writing_tools.execute(tmp_path, "book", "work", "source", selection, "WT-terminal-citation")
        applied = writing_tools.execute(tmp_path, "book", "work", "apply_revision", {"edits": [{
            "file": file, "line_start": 2, "line_end": 2, "before": "First body.",
            "after": r"First body. \cite{ScopeFixture}.", "reason": "Cite the actual read and bound fixture source."}]}, "WT-terminal-citation")
        assert applied["complete"]
        records.bank(tmp_path, {"record": "writing-reply", "id": "WR-terminal-citation", "project": "book",
            "session_id": "WS-original", "turn_id": "WT-terminal-citation", "status": "completed"})
        outline = writing_tools.execute(tmp_path, "book", "work", "structure", {"view": "outline"})
        summary = writing_tools.execute(tmp_path, "book", "work", "structure", {"view": "summary"})
        heading = next(row for row in outline["headings"]["items"] if row["heading_before"] == r"\chapter{First}")
        writing_tools.execute(tmp_path, "book", "work", "structure_change", {
            "operation": "bind_source", "section_id": "first", "file": heading["file"], "line": heading["line"],
            "heading_before": heading["heading_before"], "expected_plan_revision": summary["authority"]["plan_revision"],
            "expected_selection": outline["selected_source"]["selection_identity"],
            "expected_source_digest": outline["sources"][heading["file"]]["source_digest"]})

        def fixture_build(rendered, stamp):
            # Synthetic external compiler boundary only. Actual dependency,
            # bibliography, export and Work owners read these real fixture bytes.
            tex.with_suffix(".pdf").write_bytes(("%PDF-fixture-" + str(stamp)).encode())
            tex.with_suffix(".synctex.gz").write_bytes(b"Synthetic SyncTeX fixture")
            tex.with_suffix(".aux").write_text(r"\bibcite{ScopeFixture}{1}" if rendered else "")
            tex.with_suffix(".bbl").write_text(r"\bibitem{ScopeFixture}Actual source fixture." if rendered else "")
            pv._write_recompile_status(tex, {"state": "done", "ok": True, "finished": stamp,
                "dependencies": tex_dependencies.snapshot(tex, tmp_path),
                "outputs": pv._build_output_snapshot(tex, tmp_path),
                "pdf": tex.with_suffix(".pdf").relative_to(tmp_path).as_posix(), "built_ts": stamp})
            return document_style.export_pdf("book", tmp_path)

        pending_export = fixture_build(False, 124)
        for phase_id in ["improvement", "draft", "judgement", "synthesis", "export"]:
            task = project_work._tasks("book", tmp_path)[required[phase_id]]
            phase = next(item for item in contract["recipe"]["phases"] if item["id"] == phase_id)
            raw_parent = project_work._tasks("book", tmp_path)[parent["id"]]
            cut = prepared_work._stage_cut("book", tmp_path, raw_parent, phase)
            detail = project_work.read("book", {"view": "detail", "id": task["id"]}, tmp_path)
            writing_tools.execute(tmp_path, "book", "work", "task", {
                **detail["allowed_actions"]["task"]["payload"], "title": task["title"], "goal": task["goal"],
                "logical_target": {"kind": "writing-stage-cut", "node_id": prepared_work._digest(cut)}})
            detail = project_work.read("book", {"view": "detail", "id": task["id"]}, tmp_path)
            writing_tools.execute(tmp_path, "book", "work", "task_status", {
                **detail["allowed_actions"]["task_status"]["payload"], "status": "in-progress"})
            if phase_id == "judgement":
                guard = project_work._task_revision(project_work._tasks("book", tmp_path)[judge["id"]])
                handoff = writing_tools.execute(tmp_path, "book", "work", "work_review", {
                    "id": judge["id"], "phase": "handoff", "request_id": "external-reader-handoff",
                    "expected_work_revision": guard, "pins": {evidence[0]: pin}}, "WT-reader-handoff")
                accepted = writing_tools.execute(tmp_path, "book", "review", "work_review", {
                    "id": judge["id"], "phase": "review", "request_id": "external-reader-accept",
                    "expected_work_revision": guard, "handoff_id": handoff["phase"]["id"],
                    "obligation_id": "reader-sensitive", "verdict": "ACCEPT"}, "WT-independent-reader")
                assert accepted["phase"]["independence"] == "INDEPENDENT"
            if phase_id == "synthesis":
                writing_tools.execute(tmp_path, "book", "work", "work_review", {
                    "id": judge["id"], "phase": "synthesis", "request_id": "external-parent-synthesis",
                    "expected_work_revision": guard, "consumes": [handoff["phase"]["id"], accepted["phase"]["id"]],
                    "summary": "Original fixture parent consumes the fresh exact review."}, "WT-terminal-synthesis")
            done(task["id"], [*evidence, pending_export["file"], pending_export["receipt"]]
                 if phase_id == "export" else evidence)
        coverage = literature_support.scope("book", tmp_path, node="concept:first")
        assert "not-yet-cited" not in {g["kind"] for g in coverage["gaps"]}
        assert "citation-not-rendered" in {g["kind"] for g in coverage["gaps"]}
        assert all(project_work.read("book", {"view": "detail", "id": ident}, tmp_path)["task"]["readiness"]["satisfies_prerequisites"]
                   for ident in required.values())
        with pytest.raises(ValueError, match="Final scoped literature"):
            done(parent["id"])                # current cite text/build/export but bibliography key unrendered
        final_export = fixture_build(True, 125)
        coverage = literature_support.scope("book", tmp_path, node="concept:first")
        assert coverage["ready_for_completion"], coverage["gaps"]
        assert "ScopeFixture" in coverage["bibliography"]["rendered_keys"]
        done(exported["id"], [*evidence, final_export["file"], final_export["receipt"]])
    done(parent["id"])
    current = project_work.read("book", {"view": "detail", "id": parent["id"]}, tmp_path)["task"]
    assert current["readiness"]["satisfies_prerequisites"]

    old = project_work.read("book", {"view": "detail", "id": parent["id"]}, tmp_path)["allowed_actions"]["task_status"]["payload"]
    done(made["results"]["id"])               # new acceptance occurrence, even identical output
    with pytest.raises(ValueError, match="acceptance changed"):
        project_work.transition("book", {**old, "status": "done", "evidence": evidence}, tmp_path)
    assert not project_work.read("book", {"view": "detail", "id": parent["id"]}, tmp_path)["task"]["readiness"]["satisfies_prerequisites"]
    with pytest.raises(ValueError):
        done(parent["id"])


@pytest.mark.parametrize("mutation", ["passage", "claim", "binding"])
def test_real_support_change_invalidates_normal_stage_route_and_admission(tmp_path, monkeypatch, mutation):
    from test_literature_joined_workflow import project as real_project, bind, execute
    from laplace.research import concepts, literature_support
    manuscript, source, key, original = real_project(tmp_path, monkeypatch)
    bind(tmp_path, key)
    action = prepared_work.programme_create_action("joined", tmp_path)
    action["payload"]["section_ids"] = ["first"]
    parent = writing_tools.execute(tmp_path, "joined", "work", "task", action["payload"])
    records.bank(tmp_path, {"record": "writing-session", "id": "WS-joined-original", "project": "joined",
                            "provider": "codex", "role": "author"})
    records.bank(tmp_path, {"record": "writing-turn", "id": "WT-joined-programme", "project": "joined",
        "session_id": "WS-joined-original", "work_id": parent["id"], "mode": "work"})
    records.bank(tmp_path, {"record": "writing-reply", "id": "WR-joined-programme", "project": "joined",
        "session_id": "WS-joined-original", "turn_id": "WT-joined-programme", "status": "completed"})
    output = tmp_path / "support-interpretation.txt"
    output.write_text("Limited passage-qualified fixture support, not scientific acceptance.")
    evidence = [output.name]
    results = _stage_from_route(tmp_path, "joined", parent)
    _native_done(tmp_path, "joined", results["id"], evidence)
    support = _stage_from_route(tmp_path, "joined", parent)
    _native_done(tmp_path, "joined", support["id"], evidence)
    improvement = _stage_from_route(tmp_path, "joined", parent)
    bib = manuscript / "references.bib"
    output_before, bib_before = output.read_bytes(), bib.read_bytes() if bib.exists() else None
    from laplace.writing import turn_admission
    def admission(ident):
        task = project_work.read("joined", {"view": "detail", "id": ident}, tmp_path)["task"]
        payload = {"work_id": ident, "expected_work_scope_revision": task["work_scope_revision"],
                   "expected_dependency_revision": task["dependency_revision"]}
        return turn_admission.work_context(tmp_path, payload, {"project": "joined",
            "session_id": "WS-joined-original", "mode": "work"}, records.fold_records(tmp_path), None)
    assert admission(improvement["id"])["work_id"] == improvement["id"]
    if mutation == "passage":
        original.write_text("The first controlled claim holds only under the stated conditions. Additional limitation.\n")
    elif mutation == "claim":
        state = concepts.state("joined", "result:first", root=tmp_path)
        execute(tmp_path, "concept_change", {"operation": "edit_node", "node": "result:first",
                "base_revision": state["revision"], "value": "The controlled first claim, with its scope made explicit."})
    else:
        read = execute(tmp_path, "reference_text", {"key": key, "limit": 1000})
        execute(tmp_path, "literature_bind", {"key": key, "claim_id": "result:first",
            "relation": "supports", "rationale": "Explicit narrower scope for this actual canonical binding.",
            "reading_status": "partial", "reading_id": read["reading_receipt"]["id"],
            "evidence": {"locator": read["reading_receipt"]["locator"],
                         "excerpt": "only under the stated conditions"}})
        assert literature_support.for_node("joined", "result:first", tmp_path)["sources"][0]["rationale"] == "Explicit narrower scope for this actual canonical binding."
    changed = project_work.read("joined", {"view": "detail", "id": support["id"]}, tmp_path)["task"]
    assert changed["currentness"]["status"] != "CURRENT"
    assert not changed["readiness"]["satisfies_prerequisites"]
    assert output.read_bytes() == output_before
    assert (bib.read_bytes() if bib.exists() else None) == bib_before
    with pytest.raises(project_work.WorkConflict, match="unqualified"):
        admission(improvement["id"])
    route = prepared_work.programme_route("joined", tmp_path, parent["id"])
    assert route["next_action"]["operation"] == "task"
    assert route["next_action"]["payload"]["logical_target"]["kind"] == "writing-stage-cut"
    # Requalify changed passage/claim support, but do not undo the deliberate
    # narrower binding to its exact old accepted value.
    if mutation != "binding":
        bind(tmp_path, key)
    assert not project_work.read("joined", {"view": "detail", "id": support["id"]}, tmp_path)["task"]["readiness"]["satisfies_prerequisites"]
    # Explicit owner actions re-prepare each changed/stale predecessor and keep
    # previous specifications/completions in the existing ledger.
    for _ in range(4):
        route = prepared_work.programme_route("joined", tmp_path, parent["id"])
        action = route["next_action"]
        if action and action.get("operation") == "task" and "currentness" in action:
            updated = writing_tools.execute(tmp_path, "joined", "work", "task", action["payload"])
            task = project_work.read("joined", {"view": "detail", "id": updated["id"]}, tmp_path)
            writing_tools.execute(tmp_path, "joined", "work", "task_status", {
                **task["allowed_actions"]["task_status"]["payload"], "status": "in-progress"})
            if updated["id"] in {results["id"], support["id"]}:
                _native_done(tmp_path, "joined", updated["id"], evidence)
            else:
                break
    assert admission(improvement["id"])["work_id"] == improvement["id"]
    history = project_work._rows(tmp_path)
    assert sum(row.get("record") == "project-work" and row.get("id") == support["id"] for row in history) >= 2


def test_draft_consumes_actual_source_and_generic_work_semantics_are_unchanged(tmp_path):
    _section_fixture(tmp_path)
    parent = _ordinary_programme(tmp_path)
    (tmp_path / "stage-output.txt").write_text("Fixture interpretation.")
    for name in ["results", "literature", "improvement"]:
        if name == "improvement":
            _author_typed_reader_plan(tmp_path)
        stage = _stage_from_route(tmp_path, "book", parent)
        _native_done(tmp_path, "book", stage["id"], ["stage-output.txt"])
    draft = _stage_from_route(tmp_path, "book", parent)
    _native_done(tmp_path, "book", draft["id"], ["stage-output.txt"])
    chapter = tmp_path / "synthetics papers/book/manuscript/chapters/chapter-01.tex"
    chapter.write_text(chapter.read_text() + "\nAn actual changed source cut.\n")
    seen = project_work.read("book", {"view": "detail", "id": draft["id"]}, tmp_path)["task"]
    assert seen["currentness"]["status"] == "STALE"
    assert not seen["readiness"]["satisfies_prerequisites"]
    for kind in ["execution", "programme"]:
        ordinary = project_work.task("book", {"title": "Standalone " + kind, "goal": "Existing generic semantics",
                                             "kind": kind}, tmp_path)
        _native_done(tmp_path, "book", ordinary["id"], ["stage-output.txt"])
        assert project_work.read("book", {"view": "detail", "id": ordinary["id"]}, tmp_path)["task"]["readiness"]["satisfies_prerequisites"]


@pytest.mark.parametrize("field", ["statement_tex", "domain", "assumptions", "prerequisite"])
def test_results_bind_canonical_mathematical_meaning_not_future_documentary_inputs(tmp_path, field):
    from laplace.research import concepts, literature_support
    from laplace.writing import turn_admission
    _section_fixture(tmp_path)
    parent = _ordinary_programme(tmp_path)
    def change(operation, node, **payload):
        state = concepts.state("book", node, root=tmp_path)
        return writing_tools.execute(tmp_path, "book", "work", "concept_change", {
            "operation": operation, "node": node, "base_revision": state["revision"], **payload})
    change("set_mathematics", "concept:first", value={
        "statement_tex": "x=x", "domain": "Real numbers", "assumptions": [{"text": "A finite fixture domain."}]})
    state = concepts.state("book", root=tmp_path)
    writing_tools.execute(tmp_path, "book", "work", "concept_change", {
        "operation": "add_node", "node": "assumption:fixture", "node_kind": "postulate",
        "essence": "The explicitly stated fixture premise.", "base_revision": state["revision"]})
    change("add_edge", "concept:first", target="assumption:fixture", rel="prerequisite")
    output = tmp_path / "canonical-results-output.txt"
    output.write_text("Fixture interpretation of the explicitly authored mathematical proposition.")
    results = _stage_from_route(tmp_path, "book", parent)
    _native_done(tmp_path, "book", results["id"], [output.name])
    meaning = literature_support.meaning_revision("book", "concept:first", tmp_path)

    # Later genuine documentary import/read/bind changes are NOT results inputs.
    original = tmp_path / "future-source.txt"
    original.write_text("The fixture discusses reflexivity within its explicit domain.\n")
    imported = writing_tools.execute(tmp_path, "book", "work", "literature_import", {
        "metadata": {"title": "Reflexivity fixture", "creators": ["Fixture Author"],
                     "year": "2026", "item_type": "unpublished"},
        "provenance": {"description": "Disposable test source", "path": str(original)},
        "citekey": "FutureFixture"})
    key = imported["association"]["key"]
    read = writing_tools.execute(tmp_path, "book", "work", "reference_text", {"key": key, "limit": 1000})
    writing_tools.execute(tmp_path, "book", "work", "literature_bind", {
        "key": key, "claim_id": "concept:first", "claim_revision": meaning, "relation": "supports",
        "rationale": "Limited fixture documentary context only.", "reading_status": "partial",
        "reading_id": read["reading_receipt"]["id"],
        "evidence": {"locator": read["reading_receipt"]["locator"], "excerpt": "within its explicit domain"}})
    assert literature_support.meaning_revision("book", "concept:first", tmp_path) == meaning
    assert project_work.read("book", {"view": "detail", "id": results["id"]}, tmp_path)["task"]["readiness"]["satisfies_prerequisites"]
    support = _stage_from_route(tmp_path, "book", parent)
    source = tmp_path / "synthetics papers/book/manuscript"
    bibs = {p: p.read_bytes() for p in source.glob("*.bib")}
    output_before = output.read_bytes()
    raw = project_work._tasks("book", tmp_path)[results["id"]]
    result_bindings = list(raw["manuscript_stage"]["cut"]["support"]["nodes"])
    def admit(ident):
        row = project_work.read("book", {"view": "detail", "id": ident}, tmp_path)["task"]
        return turn_admission.work_context(tmp_path, {"work_id": ident,
            "expected_work_scope_revision": row["work_scope_revision"],
            "expected_dependency_revision": row["dependency_revision"]},
            {"project": "book", "session_id": "WS-original", "mode": "work"},
            records.fold_records(tmp_path), None)
    assert admit(support["id"])["work_id"] == support["id"]
    if field == "prerequisite":
        change("edit_node", "assumption:fixture", value="A changed prerequisite proposition with an explicit narrower meaning.")
    else:
        value = {"statement_tex": "x=x", "domain": "Real numbers",
                 "assumptions": [{"text": "A finite fixture domain."}]}
        value[field] = {"statement_tex": "x+0=x", "domain": "Nonnegative real numbers",
                        "assumptions": [{"text": "A different explicit fixture assumption."}]}[field]
        change("set_mathematics", "concept:first", value=value)
    assert literature_support.meaning_revision("book", "concept:first", tmp_path) != meaning
    assert output.read_bytes() == output_before
    assert {p: p.read_bytes() for p in source.glob("*.bib")} == bibs
    # No interpretation/result-output binding or unrelated prose was edited.
    assert project_work._tasks("book", tmp_path)[results["id"]]["manuscript_stage"]["cut"]["support"]["nodes"] == result_bindings
    changed = project_work.read("book", {"view": "detail", "id": results["id"]}, tmp_path)["task"]
    assert changed["currentness"]["status"] == "STALE"
    assert not changed["readiness"]["satisfies_prerequisites"]
    with pytest.raises(project_work.WorkConflict, match="unqualified"):
        admit(support["id"])
    action = prepared_work.programme_route("book", tmp_path, parent["id"])["next_action"]
    assert action["operation"] == "task" and action["payload"]["id"] == results["id"]
    writing_tools.execute(tmp_path, "book", "work", "task", action["payload"])
    detail = project_work.read("book", {"view": "detail", "id": results["id"]}, tmp_path)
    writing_tools.execute(tmp_path, "book", "work", "task_status", {
        **detail["allowed_actions"]["task_status"]["payload"], "status": "in-progress"})
    _native_done(tmp_path, "book", results["id"], [output.name])
    assert project_work.read("book", {"view": "detail", "id": results["id"]}, tmp_path)["task"]["readiness"]["satisfies_prerequisites"]
    assert sum(row.get("record") == "project-work" and row.get("id") == results["id"]
               for row in project_work._rows(tmp_path)) >= 2

# Historical logical targets are data, not an implicit manuscript opt-in.
_LEGACY_TARGETS = [
    ("missing", None), ("string", "concept:legacy-completed"), ("none", None),
    ("empty-list", []), ("list", ["concept:legacy"]), ("number", 17),
    ("false", False), ("empty-object", {}), ("none-kind", {"kind": None}),
    ("number-kind", {"kind": 7}), ("list-kind", {"kind": ["writing-programme"]}),
    ("object-kind", {"kind": {"name": "writing-programme"}}),
]


def _historical_target_work(root, target, *, kind="execution", missing=False):
    """Seed a legitimate historical shape, then complete through the real owner."""
    task = project_work.task("book", {"title": "Historical target fixture", "goal": "Ordinary scoped outcome.",
                                    "kind": kind}, root)
    row = project_work._tasks("book", root)[task["id"]]
    if not missing:
        row["logical_target"] = target
    project_work._append(root, row)  # historical input, not a migration or derived-view mock
    output = root / "legacy-target-output.txt"
    output.write_text("Retained ordinary completion evidence.\n")
    _native_done(root, "book", task["id"], [output.name])
    return task["id"]


@pytest.mark.parametrize("kind", ["execution", "programme"])
@pytest.mark.parametrize("case,target", _LEGACY_TARGETS, ids=[item[0] for item in _LEGACY_TARGETS])
def test_legacy_targets_remain_ordinary_through_real_detail_summary_pipeline_http(tmp_path, case, target, kind):
    from laplace.web import project_work_surface
    import hashlib
    _section_fixture(tmp_path)
    ident = _historical_target_work(tmp_path, target, kind=kind, missing=case == "missing")
    neighbour = project_work.task("book", {"title": "Ordinary neighbour", "goal": "Stay readable."}, tmp_path)
    row = project_work._tasks("book", tmp_path)[ident]
    # Reproduce the pre-opt-in specification identity exactly, without calling
    # the new classifier. Reads must neither normalise targets nor rescope Work.
    keys = ("id", "title", "goal", "task_kind", "parent_work_id", "depends_on",
            "section_ids", "anchor", "obligation_id", "logical_target")
    old_hash = "sha256:" + hashlib.sha256(json.dumps({key: row.get(key) for key in keys},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert project_work._task_revision(row) == old_hash
    basis = project_work._work_basis(project_work._tasks("book", tmp_path), ident)[0]
    before = project_work._ledger(tmp_path).read_bytes()
    detail = writing_tools.execute(tmp_path, "book", "work", "project", {"view": "detail", "id": ident})
    assert detail["task"]["work_revision"] == old_hash
    assert detail["task"]["work_scope_revision"] == basis["scope_revision"]
    assert detail["task"]["readiness"]["satisfies_prerequisites"]
    assert detail["task"]["currentness"]["status"] == "CURRENT"
    assert "manuscript_programme" not in detail["task"] and "manuscript_stage" not in detail["task"]
    summary = project_work.summary("book", tmp_path)
    assert any(item["id"] == ident for item in summary["tasks"])
    pipeline = writing_tools.execute(tmp_path, "book", "work", "pipeline", {})
    assert pipeline["programme"]["routes"] == []
    for route, query in [
            ("/work/state", {"project": ["book"], "view": ["detail"], "id": [ident]}),
            ("/work/pipeline", {"project": ["book"]})]:
        code, _, raw = project_work_surface.handle(route, query, "GET", repo_root=tmp_path)
        assert code == 200, raw
        observed = json.loads(raw)
        if route == "/work/state":
            assert observed["task"]["work_revision"] == old_hash
            assert observed["task"]["readiness"]["satisfies_prerequisites"]
        else:
            assert observed["programme"]["routes"] == []
    assert project_work.read("book", {"view": "detail", "id": neighbour["id"]}, tmp_path)["task"]["status"] == "ready"
    assert project_work._ledger(tmp_path).read_bytes() == before
    retained = project_work._tasks("book", tmp_path)[ident]
    assert ("logical_target" in retained) is (case != "missing")
    if case != "missing":
        assert retained["logical_target"] == target


_MALFORMED_CONTRACTS = [
    ("programme-none", "manuscript_programme", None),
    ("programme-list", "manuscript_programme", []),
    ("programme-string", "manuscript_programme", "not-a-contract"),
    ("programme-number", "manuscript_programme", 3),
    ("programme-empty", "manuscript_programme", {}),
    ("stage-none", "manuscript_stage", None),
    ("stage-list", "manuscript_stage", ["phase"]),
    ("stage-string", "manuscript_stage", "not-a-stage"),
    ("stage-number", "manuscript_stage", 3),
    ("stage-empty", "manuscript_stage", {}),
]


def _assert_invalid_contract_owners(root, ident, *, programme=False, required_parent=None):
    from laplace.web import project_work_surface
    detail = writing_tools.execute(root, "book", "work", "project", {"view": "detail", "id": ident})
    task = detail["task"]
    assert task["currentness"]["kind"] == "MANUSCRIPT_CONTRACT_INVALID"
    assert task["currentness"]["status"] == "UNKNOWN"
    assert "Invalid manuscript contract:" in task["currentness"]["reason"]
    assert task["status"] == "blocked" and not task["readiness"]["satisfies_prerequisites"]
    assert "done" in detail["allowed_actions"]["task_status"]["refused"]
    with pytest.raises(ValueError, match="Invalid manuscript contract"):
        writing_tools.execute(root, "book", "work", "task_status", {
            **detail["allowed_actions"]["task_status"]["payload"], "status": "done",
            "evidence": ["legacy-target-output.txt"]})
    with pytest.raises(project_work.WorkConflict, match="Invalid manuscript contract"):
        project_work.context("book", ident, root)
    summary = project_work.summary("book", root)
    assert any(row["id"] == ident for row in summary["tasks"])
    pipeline = writing_tools.execute(root, "book", "work", "pipeline", {})
    def assert_invalid_route(value):
        if not programme and required_parent is None:
            return  # standalone malformed stage is not a programme route
        route_id = ident if programme else required_parent
        invalid = next(row for row in value["programme"]["routes"] if row["work_id"] == route_id)
        assert invalid["issues"] and invalid["next_action"] is None and invalid["join_action"] is None
        if required_parent:
            issue = next(row for row in invalid["invalid_stage_reads"] if row["work_id"] == ident)
            assert issue["kind"] == "MANUSCRIPT_CONTRACT_INVALID"
            assert issue["read"] == task["read_handle"]
            assert any(ident in text and "Invalid manuscript contract:" in text for text in invalid["issues"])
    assert_invalid_route(pipeline)
    for route, query in [
            ("/work/state", {"project": ["book"], "view": ["detail"], "id": [ident]}),
            ("/work/pipeline", {"project": ["book"]})]:
        code, _, raw = project_work_surface.handle(route, query, "GET", repo_root=root)
        assert code == 200, raw
        if route == "/work/state":
            assert not json.loads(raw)["task"]["readiness"]["satisfies_prerequisites"]
        else:
            assert_invalid_route(json.loads(raw))


@pytest.mark.parametrize("recorded", ["open", "done"])
@pytest.mark.parametrize("case,field,value", _MALFORMED_CONTRACTS, ids=[item[0] for item in _MALFORMED_CONTRACTS])
def test_malformed_explicit_contracts_are_local_held_not_global_crash(tmp_path, recorded, case, field, value):
    _section_fixture(tmp_path)
    ident = _historical_target_work(tmp_path, "legacy-target")
    row = project_work._tasks("book", tmp_path)[ident]
    row[field] = value
    row["status"] = recorded
    if field == "manuscript_programme":
        row["task_kind"] = "programme"
        row["logical_target"] = {"kind": "writing-programme"}
    project_work._append(tmp_path, row)
    neighbour = project_work.task("book", {"title": "Unaffected neighbour", "goal": "Stay ordinary."}, tmp_path)
    before = project_work._ledger(tmp_path).read_bytes()
    _assert_invalid_contract_owners(tmp_path, ident, programme=field == "manuscript_programme")
    assert project_work.read("book", {"view": "detail", "id": neighbour["id"]}, tmp_path)["task"]["status"] == "ready"
    assert project_work._ledger(tmp_path).read_bytes() == before


@pytest.mark.parametrize("malformation", [
    "required-list", "required-value-list", "recipe-list", "phase-string",
    "phase-deps-list", "phase-reviews-list", "scope-list",
    "stage-phase-list", "stage-cut-list", "stage-support-list"])
def test_malformed_nested_optin_shapes_refuse_without_hiding_mixed_project(tmp_path, malformation):
    import copy
    _section_fixture(tmp_path)
    parent = _ordinary_programme(tmp_path)
    first = _stage_from_route(tmp_path, "book", parent)
    ident = first["id"] if malformation.startswith("stage-") else parent["id"]
    row = copy.deepcopy(project_work._tasks("book", tmp_path)[ident])
    contract = row.get("manuscript_programme")
    if malformation == "required-list":
        contract["required_stages"] = []
    elif malformation == "required-value-list":
        contract["required_stages"]["results"] = ["not-an-id"]
    elif malformation == "recipe-list":
        contract["recipe"] = []
    elif malformation == "phase-string":
        contract["recipe"]["phases"][0] = "results"
    elif malformation == "phase-deps-list":
        contract["recipe"]["phases"][1]["depends_on"] = [["results"]]
    elif malformation == "phase-reviews-list":
        contract["recipe"]["phases"][4]["review_obligations"] = ["reader-sensitive"]
    elif malformation == "scope-list":
        row["logical_target"]["node_id"] = ["concept:first"]
    elif malformation == "stage-phase-list":
        row["manuscript_stage"]["phase_id"] = ["results"]
    elif malformation == "stage-cut-list":
        row["manuscript_stage"]["cut"] = []
    elif malformation == "stage-support-list":
        row["manuscript_stage"]["cut"]["support"] = []
    project_work._append(tmp_path, row)
    neighbour = project_work.task("book", {"title": "Nested-shape neighbour", "goal": "Stay ordinary."}, tmp_path)
    before = project_work._ledger(tmp_path).read_bytes()
    scope = project_work._work_basis(project_work._tasks("book", tmp_path), ident)[0]["scope_revision"]
    _assert_invalid_contract_owners(tmp_path, ident, programme=ident == parent["id"],
                                   required_parent=parent["id"] if ident == first["id"] else None)
    assert project_work.read("book", {"view": "detail", "id": neighbour["id"]}, tmp_path)["task"]["status"] == "ready"
    assert project_work._ledger(tmp_path).read_bytes() == before
    assert project_work._work_basis(project_work._tasks("book", tmp_path), ident)[0]["scope_revision"] == scope


@pytest.mark.parametrize("recorded", ["open", "done"])
@pytest.mark.parametrize("value", [None, [], "not-a-stage", 3, {}], ids=["none", "list", "string", "number", "object"])
def test_malformed_required_stage_never_advertises_rejected_reprepare(tmp_path, recorded, value):
    _section_fixture(tmp_path)
    parent = _ordinary_programme(tmp_path)
    first = _stage_from_route(tmp_path, "book", parent)
    row = project_work._tasks("book", tmp_path)[first["id"]]
    row["manuscript_stage"] = value
    row["status"] = recorded
    project_work._append(tmp_path, row)
    neighbour = project_work.task("book", {"title": "Required-stage neighbour", "goal": "Stay readable."}, tmp_path)
    before = project_work._ledger(tmp_path).read_bytes()
    scope = project_work._work_basis(project_work._tasks("book", tmp_path), first["id"])[0]["scope_revision"]
    _assert_invalid_contract_owners(tmp_path, first["id"], required_parent=parent["id"])
    assert project_work.read("book", {"view": "detail", "id": neighbour["id"]}, tmp_path)["task"]["status"] == "ready"
    assert project_work._ledger(tmp_path).read_bytes() == before
    assert project_work._work_basis(project_work._tasks("book", tmp_path), first["id"])[0]["scope_revision"] == scope


@pytest.mark.parametrize("door", ["native", "http"])
def test_valid_stale_required_cut_still_offers_executable_repreparation(tmp_path, door):
    from laplace.web import project_work_surface
    from laplace.research import concepts
    _section_fixture(tmp_path)
    parent = _ordinary_programme(tmp_path)
    first = _stage_from_route(tmp_path, "book", parent)
    (tmp_path / "stale-valid-output.txt").write_text("Fixture interpretation.")
    _native_done(tmp_path, "book", first["id"], ["stale-valid-output.txt"])
    state = concepts.state("book", "concept:first", root=tmp_path)
    writing_tools.execute(tmp_path, "book", "work", "concept_change", {
        "operation": "edit_node", "node": "concept:first", "base_revision": state["revision"],
        "value": "An explicitly changed authored fixture definition."})
    detail = project_work.read("book", {"view": "detail", "id": first["id"]}, tmp_path)
    assert detail["task"]["currentness"]["status"] == "STALE"
    before = project_work._ledger(tmp_path).read_bytes()
    scope = detail["task"]["work_scope_revision"]
    if door == "native":
        pipeline = writing_tools.execute(tmp_path, "book", "work", "pipeline", {})
    else:
        code, _, raw = project_work_surface.handle("/work/pipeline", {"project": ["book"]}, "GET", repo_root=tmp_path)
        assert code == 200
        pipeline = json.loads(raw)
    route = next(row for row in pipeline["programme"]["routes"] if row["work_id"] == parent["id"])
    assert route["invalid_stage_reads"] == []
    action = route["next_action"]
    assert action["operation"] == "task" and action["payload"]["id"] == first["id"]
    assert action["currentness"]["status"] == "STALE"
    assert project_work._ledger(tmp_path).read_bytes() == before
    assert project_work.read("book", {"view": "detail", "id": first["id"]}, tmp_path)["task"]["work_scope_revision"] == scope
    if door == "native":
        updated = writing_tools.execute(tmp_path, "book", "work", "task", action["payload"])
    else:
        code, _, raw = project_work_surface.handle("/work/task", {}, "POST",
            json.dumps({"project": "book", **action["payload"]}).encode(), tmp_path)
        assert code == 201, raw  # existing /work/task append owner, also for guarded edits
        updated = json.loads(raw)
    assert updated["id"] == first["id"]
    raw = project_work._tasks("book", tmp_path)[first["id"]]
    assert prepared_work.stage_currentness(raw, project_work._tasks("book", tmp_path), tmp_path)["status"] == "CURRENT"
    # Deliberate guarded preparation changes the consumed scope, never silently
    # renews the old completion. The standing still needs explicit execution.
    assert updated["work_scope_revision"] != scope


def _author_typed_reader_plan(root, section_ids=('first',), count=1):
    """Author through typed owners, then acknowledge every current input cut.
    No forged qualified JSON, provider judgement or final-prose prerequisite."""
    for sid in section_ids:
        view=project_structure.read('book',{'view':'detail','section_ids':[sid]},root)['sections'][0]
        writing_tools.execute(root,'book','work','structure_change',{
            **view['reader_transition']['edit_action']['payload'],
            'changes':{'function':'Explain the construction','question_answered':'What is retained?',
                       'entry_state':'Knows the controlled question','exit_state':'Can use the result'}})
        ids=[]
        for number in range(count):
            view=project_structure.read('book',{'view':'detail','section_ids':[sid]},root)['sections'][0]
            saved=writing_tools.execute(root,'book','work','structure_change',{
                **view['paragraph_plan']['create_action']['payload'],
                'changes':{'function':'Explain','proposition':'Controlled proposition '+str(number)}})
            ids.append(saved['paragraph_id'])
        # Appending a neighbour can stale an earlier row. Deliberate exact
        # owner acknowledgements make ALL rows current, not just the first page.
        for ident in ids:
            view=project_structure.read('book',{'view':'detail','section_ids':[sid],
                'paragraph_id':ident},root)['sections'][0]
            row=view['paragraph_plan']['paragraphs']['items'][0]
            writing_tools.execute(root,'book','work','structure_change',{
                **row['edit_action']['payload'],'changes':{},
                'input_observations':row['edit_action']['payload']['expected_reader_basis']['inputs']})
    return ids


def _improvement_fixture(root):
    _section_fixture(root)
    parent=_ordinary_programme(root)
    (root/'typed-stage-output.txt').write_text('A scoped fixture interpretation, not acceptance of exposition.')
    for _ in range(2):
        stage=_stage_from_route(root,'book',parent)
        _native_done(root,'book',stage['id'],['typed-stage-output.txt'])
    stage=_stage_from_route(root,'book',parent)
    assert stage['manuscript_stage']['phase_id']=='improvement'
    return parent,stage


def _refresh_typed_stage(root,parent,stage):
    tasks=project_work._tasks('book',root)
    phase=next(p for p in tasks[parent['id']]['manuscript_programme']['recipe']['phases']
               if p['id']=='improvement')
    cut=prepared_work._stage_cut('book',root,tasks[parent['id']],phase)
    current=project_work.read('book',{'view':'detail','id':stage['id']},root)
    writing_tools.execute(root,'book','work','task',{
        **current['allowed_actions']['task']['payload'],'title':stage['title'],'goal':stage['goal'],
        'logical_target':{'kind':'writing-stage-cut','node_id':prepared_work._digest(cut)}})
    return project_work._tasks('book',root)[stage['id']]


@pytest.mark.parametrize('state',['missing','notes-only','incomplete'])
def test_typed_reader_improvement_admits_work_but_completion_requires_rich_plan(tmp_path,state):
    parent,stage=_improvement_fixture(tmp_path)
    if state=='notes-only':
        path=tmp_path/'synthetics papers/book/manuscript/projection_plan.json'
        plan=json.loads(path.read_text());plan['sections'][0]['notes']='A notes-only scaffold is not a contract.'
        path.write_text(json.dumps(plan))
    elif state=='incomplete':
        view=project_structure.read('book',{'view':'detail','section_ids':['first']},tmp_path)['sections'][0]
        writing_tools.execute(tmp_path,'book','work','structure_change',{
            **view['reader_transition']['edit_action']['payload'],'changes':{'entry_state':'Only one field'}})
    raw=_refresh_typed_stage(tmp_path,parent,stage)
    tasks=project_work._tasks('book',tmp_path)
    assert prepared_work.stage_currentness(raw,tasks,tmp_path)['status']=='CURRENT'
    # The existing admission hook deliberately does not require qualification.
    project_work.context('book',stage['id'],tmp_path)
    with pytest.raises(ValueError,match='(reader|Reader)'):
        _native_done(tmp_path,'book',stage['id'],['typed-stage-output.txt'])
    assert prepared_work.stage_currentness(raw,tasks,tmp_path,require_qualified=True)['status']=='UNKNOWN'


def test_typed_reader_actual_current_complete_plan_qualifies_without_prose_cycle(tmp_path):
    from laplace.manuscript import bindings
    parent,stage=_improvement_fixture(tmp_path)
    _author_typed_reader_plan(tmp_path)
    raw=_refresh_typed_stage(tmp_path,parent,stage)
    tasks=project_work._tasks('book',tmp_path)
    assert prepared_work.stage_currentness(raw,tasks,tmp_path,require_qualified=True)['status']=='CURRENT'
    _native_done(tmp_path,'book',stage['id'],['typed-stage-output.txt'])
    chapter=tmp_path/'synthetics papers/book/manuscript/chapters/chapter-01.tex'
    chapter.write_text(chapter.read_text()+'\nA later authorised prose draft.\n')
    outline=writing_tools.execute(tmp_path,'book','work','structure',{'view':'outline'})
    summary=writing_tools.execute(tmp_path,'book','work','structure',{'view':'summary'})
    heading=next(h for h in outline['headings']['items'] if h['heading_before']=='\\chapter{First}')
    writing_tools.execute(tmp_path,'book','work','structure_change',{'operation':'bind_source','section_id':'first',
        'file':heading['file'],'line':heading['line'],'heading_before':heading['heading_before'],
        'expected_plan_revision':summary['authority']['plan_revision'],
        'expected_selection':outline['selected_source']['selection_identity'],
        'expected_source_digest':outline['sources'][heading['file']]['source_digest']})
    tasks=project_work._tasks('book',tmp_path)
    assert prepared_work.stage_currentness(tasks[stage['id']],tasks,tmp_path,require_qualified=True)['status']=='CURRENT'
    assert project_work.read('book',{'view':'detail','id':stage['id']},tmp_path)['task']['readiness']['satisfies_prerequisites']


def test_typed_reader_complete_scope_includes_late_paragraph_not_first_page(tmp_path):
    parent,stage=_improvement_fixture(tmp_path)
    ids=_author_typed_reader_plan(tmp_path,count=25)
    row=project_structure.read('book',{'view':'detail','section_ids':['first'],
        'paragraph_id':ids[-1]},tmp_path)['sections'][0]['paragraph_plan']['paragraphs']['items'][0]
    writing_tools.execute(tmp_path,'book','work','structure_change',{
        **row['edit_action']['payload'],'changes':{'function':''}})
    raw=_refresh_typed_stage(tmp_path,parent,stage)
    with pytest.raises(ValueError,match='(reader|Reader)'):
        _native_done(tmp_path,'book',stage['id'],['typed-stage-output.txt'])
    readiness=raw['manuscript_stage']['cut']['reader_readiness']
    first=readiness['sections'][0]
    assert first['paragraph_total']==25 and first['paragraphs_observed']==25
    assert readiness['status']=='INCOMPLETE'


@pytest.mark.parametrize('damage',['unpin','stale','unavailable'])
def test_typed_reader_unpinned_stale_unavailable_cannot_complete(tmp_path,monkeypatch,damage):
    from laplace.manuscript import reader_plan
    parent,stage=_improvement_fixture(tmp_path)
    _author_typed_reader_plan(tmp_path)
    if damage=='unpin':
        # Remove retained observations, not fabricate a success marker.
        monkeypatch.setattr(reader_plan,'_standing',lambda *a,**k:{'status':'UNPINNED','changed_inputs':[]})
    elif damage=='stale':
        state=writing_tools.execute(tmp_path,'book','work','concept',{'node':'concept:first'})
        writing_tools.execute(tmp_path,'book','work','concept_change',{'operation':'edit_node',
            'node':'concept:first','base_revision':state['revision'],'value':'A changed planning premise.'})
    else:
        original=project_structure.read
        def absent(project,payload,root):
            if payload.get('view')=='detail':raise ValueError('Reader owner fixture unavailable')
            return original(project,payload,root)
        monkeypatch.setattr(project_structure,'read',absent)
    raw=_refresh_typed_stage(tmp_path,parent,stage)
    tasks=project_work._tasks('book',tmp_path)
    assert prepared_work.stage_currentness(raw,tasks,tmp_path,require_qualified=True)['status']=='UNKNOWN'


def test_typed_reader_whole_route_empty_scope_is_not_an_na_waiver(tmp_path):
    parent,stage=_improvement_fixture(tmp_path)
    tasks=project_work._tasks('book',tmp_path)
    raw_parent={**tasks[parent['id']],'section_ids':[]}
    phase=next(p for p in raw_parent['manuscript_programme']['recipe']['phases'] if p['id']=='improvement')
    cut=prepared_work._stage_cut('book',tmp_path,raw_parent,phase)
    assert cut['reader_readiness']['scope']['kind']=='whole-reader-plan'
    assert set(cut['reader_readiness']['scope']['section_ids'])=={'first','first-child','second'}
    assert cut['reader_readiness']['status']=='INCOMPLETE'
    path=tmp_path/'synthetics papers/book/manuscript/projection_plan.json'
    plan=json.loads(path.read_text());plan['sections']=[];path.write_text(json.dumps(plan))
    cut=prepared_work._stage_cut('book',tmp_path,raw_parent,phase)
    assert cut['reader_readiness']['status']=='INCOMPLETE'
    assert any('reader' in p.lower() for p in cut['problems'])
    assert prepared_work.stage_currentness({'id':'manual'}, {},tmp_path,require_qualified=True) is None


def test_typed_reader_cut_is_stable_and_tracks_actual_inputs_while_already_stale(tmp_path):
    parent,stage=_improvement_fixture(tmp_path)
    _author_typed_reader_plan(tmp_path)
    _refresh_typed_stage(tmp_path,parent,stage)
    tasks=project_work._tasks('book',tmp_path)
    raw_parent=tasks[parent['id']]
    phase=next(p for p in raw_parent['manuscript_programme']['recipe']['phases'] if p['id']=='improvement')
    original=prepared_work._stage_cut('book',tmp_path,raw_parent,phase)
    for _ in range(3):
        assert prepared_work._stage_cut('book',tmp_path,raw_parent,phase)==original
    cuts=[]
    for meaning in ['A changed planning premise once.','A changed planning premise twice.']:
        current=writing_tools.execute(tmp_path,'book','work','concept',{'node':'concept:first'})
        writing_tools.execute(tmp_path,'book','work','concept_change',{'operation':'edit_node',
            'node':'concept:first','base_revision':current['revision'],'value':meaning})
        cut=prepared_work._stage_cut('book',tmp_path,raw_parent,phase)
        assert cut['reader_readiness']['status']=='INCOMPLETE'
        assert prepared_work._stage_cut('book',tmp_path,raw_parent,phase)==cut
        cuts.append(cut)
    a,b=[c['reader_readiness']['sections'][0]['contract'] for c in cuts]
    assert a['currentness']['status']==b['currentness']['status']=='STALE'
    assert a['basis']['inputs']!=b['basis']['inputs']
    assert cuts[0]['reader_inputs']!=cuts[1]['reader_inputs']
    # Only stable owner substance, no fresh control IDs or whole responses.
    wire=json.dumps(original['reader_readiness'])
    assert 'edit_action' not in wire and 'RPUB-' not in wire and 'observation_id' not in wire
