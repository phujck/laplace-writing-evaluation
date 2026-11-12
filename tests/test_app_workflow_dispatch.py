"""Public synthetic owners and deterministic capabilities, never provider inference."""
import copy
import json
from contextlib import contextmanager

import pytest
import runtime_guard

from laplace.pipeline import workflow_definitions as D
from laplace.writing import records, child_hosts, workflow_dispatch as A, provider
from laplace.work import project_work as W, owner_discovery as O
from laplace.projects import artifacts


BODY = {'schema_version': D.SCHEMA, 'title': 'A reusable builder and review', 'settings': {
    'provider': 'codex', 'model': 'fixture-model', 'effort': 'low'}, 'steps': [
    {'id': '0builder', 'parent_id': None, 'assignment': {'role': 'builder', 'instructions': 'Full builder instructions.\n' + 'Paragraph. ' * 200}},
    {'id': 'Review', 'parent_id': None, 'assignment': {'role': 'adversary', 'instructions': 'Independently review the exact builder result.'}},
    {'id': 'synthesis', 'parent_id': None, 'assignment': {'role': 'synthesis', 'instructions': 'Authored synthesis must not disappear.'}}],
    'edges': [{'id': 'review-edge', 'from': '0builder', 'to': 'Review', 'kind': 'control'}]}


@pytest.fixture
def prepared(tmp_path, monkeypatch, register_project):
    runtime_guard.arm(monkeypatch)
    monkeypatch.delenv('LAPLACE_CUSTODY_LIVE', raising=False)
    register_project(tmp_path, 'book')
    catalogue = {'providers': [{'id': 'codex', 'available': True, 'models': [
        {'id': 'fixture-model', 'default_effort': 'low', 'efforts': ['low']}]}]}
    monkeypatch.setattr(provider, 'capabilities', lambda *a, **k: catalogue)
    from laplace.writing import provider_catalogue
    monkeypatch.setattr(provider_catalogue, 'provider_catalogue', lambda *a: catalogue)
    records.bank(tmp_path, {'record': 'writing-session', 'id': 'WS-parent', 'project': 'book', 'role': 'author', 'provider': 'codex'})
    records.bank(tmp_path, {'record': 'writing-turn', 'id': 'prepare-turn', 'session_id': 'WS-parent', 'project': 'book', 'mode': 'work'})
    child_hosts._begin_child_execution(tmp_path, 'WS-parent', {'state': 'RUNNING', 'turn_id': 'prepare-turn',
        'project': 'book', 'session_id': 'WS-parent', 'host': child_hosts._process_identity()})
    saved = D.save(tmp_path, O.project_scope('book', 'sdk'), {'request_id': 'save-body', 'expected_revision': None, 'definition': copy.deepcopy(BODY)})
    caller = D.native_caller(tmp_path, 'book', 'work', 'prepare-turn')
    payload = {'profile': D.APP_PROFILE, 'request_id': 'prepare-request', 'reference': saved['reference'],
        'step_ids': ['0builder', 'Review'], 'goal': 'Return an independently reviewed public result', 'fan_out_max': 2}
    return tmp_path, caller, payload, saved


def test_exact_app_preparation_pin_replay_and_separate_current_head(prepared):
    root, caller, payload, saved = prepared
    result = D.prepare(root, caller, payload)
    assert result['effect'] == 'prepared' and result['status'] == 'NOT_STARTED' and not result['provider_started']
    plan, pin, artifact = A._checked(root, 'book', W._tasks('book', root)[result['work']['id']])
    assert plan['packets'][0]['brief'] == BODY['steps'][0]['assignment']['instructions']
    assert pin['step_packets']['0builder'].startswith('step-') and pin['reference'] == saved['reference']
    assert len([row for row in W._tasks('book', root).values() if row['task_kind'] == 'dispatch']) == 1
    changed = copy.deepcopy(BODY); changed['settings']['effort'] = 'high'; changed['title'] = 'New head'
    D.save(root, O.project_scope('book', 'sdk'), {'request_id': 'new-head', 'definition_id': saved['definition_id'],
        'expected_revision': saved['version'], 'definition': changed})
    replay = D.prepare(root, caller, payload)
    assert replay['receipt'] == result['receipt'] and replay['replayed']
    assert artifacts.resolve_path(root, 'book', plan['packets'][0]['return_path']).is_file() is False
    assert A._checked(root, 'book', W._tasks('book', root)[result['work']['id']])[1]['settings_digest'] == pin['settings_digest']
    assert len(records.fold_records(root)['sessions']) == len(records.fold_records(root)['turns']) == 1
    request = D.read(root, caller, {'facet': 'request', 'request_id': payload['request_id']})
    assert request['status'] == 'RECORDED' and request['receipt'] == result['receipt']
    (root / 'prepare-proof.json').write_text(json.dumps({'first': result, 'replay': replay, 'plan': plan}, indent=2))


def test_artifact_then_work_interruption_recovers_once(prepared, monkeypatch):
    root, caller, payload, _ = prepared
    original = W.task
    monkeypatch.setattr(W, 'task', lambda *a, **k: (_ for _ in ()).throw(OSError('Work publication interrupted')))
    with pytest.raises(D.Refused, match='APP_PREPARATION_PARTIAL') as failure:
        D.prepare(root, caller, payload)
    assert failure.value.details['effect'] == 'partial'
    assert D.read(root, caller, {'facet': 'request', 'request_id': payload['request_id']})['status'] == 'PARTIAL'
    monkeypatch.setattr(W, 'task', original)
    result = D.prepare(root, caller, payload)
    assert result['effect'] == 'prepared' and result['replayed']
    assert len([row for row in records.index(root).by_project['book'] if row['record'] == 'writing-artifact']) == 1
    assert len(W._tasks('book', root)) == 1


def test_banked_before_file_recovers_original_artifact_and_later_inverse_refuses(prepared, monkeypatch):
    root, caller, payload, _ = prepared
    original = __import__('pathlib').Path.replace
    def interrupted(path, target):
        if str(path).endswith('.pending'):
            raise OSError('After ART bank, before file')
        return original(path, target)
    monkeypatch.setattr(__import__('pathlib').Path, 'replace', interrupted)
    with pytest.raises(D.Refused, match='APP_PREPARATION_PARTIAL'):
        D.prepare(root, caller, payload)
    monkeypatch.setattr(__import__('pathlib').Path, 'replace', original)
    result = D.prepare(root, caller, payload)
    work = W._tasks('book', root)[result['work']['id']]
    _, pin, saved = A._checked(root, 'book', work)
    path = artifacts.target(root, 'book', {'id': saved['id']})[0]
    artifacts.restore_owned_absence(root, 'book', path, saved['revision'], {'inverse': True})
    with pytest.raises(D.Refused, match='APP_PREPARATION_UNAVAILABLE|REQUEST_CONFLICT'):
        D.prepare(root, caller, payload)
    assert not path.exists()
    assert len([row for row in records.index(root).by_project['book'] if row['record'] == 'writing-artifact']) == 2


@pytest.mark.parametrize('change,code', [
    # A selected synthesis is the original parent's own step (parent_synthesis), not an unsupported child:
    # its declared settings must match the initiating conversation, which here has none of them.
    ({'step_ids': ['0builder', 'Review', 'synthesis'], 'fan_out_max': 3}, 'PARENT_SYNTHESIS_SETTINGS_CONFLICT'),
    ({'goal': 'Different same request intent'}, 'REQUEST_CONFLICT')])
def test_selected_synthesis_and_changed_intent_are_local(prepared, change, code):
    root, caller, payload, _ = prepared
    if code == 'REQUEST_CONFLICT':
        D.prepare(root, caller, payload)
    with pytest.raises(D.Refused, match=code) as failure:
        D.prepare(root, caller, {**payload, **change})
    if code == 'PARENT_SYNTHESIS_SETTINGS_CONFLICT':
        assert failure.value.details['field'] == 'model' and failure.value.details['required'] == 'fixture-model'
        assert not W._tasks('book', root)


def test_composer_and_bounded_reads_preserve_exact_version_without_effects(prepared):
    root, caller, payload, saved = prepared
    query = {'facet': 'app-compose', 'definition_id': saved['definition_id'], 'version': saved['version'],
        **{key: payload[key] for key in ('request_id', 'step_ids', 'goal', 'fan_out_max')}}
    composed = D.read(root, O.owned_workspace('http'), query)
    assert composed['prepare_payload'] == {'action': 'prepare', **payload}
    assert composed['action']['send_required'] and 'workflow_action_read=' in composed['action']['project_url']
    assert not W._tasks('book', root)
    result = D.prepare(root, caller, payload)
    listing = D.read(root, caller, {'facet': 'app-runs', 'reference': saved['reference']})
    run = D.read(root, caller, listing['items'][0]['read']['request'])
    assert run['parent']['prepared_by']['turn_id'] == 'prepare-turn' and run['parent']['launched_by'] is None
    assert all(step['state'] == 'NOT_STARTED' for step in run['steps'])
    assert run['actions']['use_in_conversation']['payload']['session_id'] == 'WS-parent'
    assert result['run']['reference'] == saved['reference']


def test_prepared_dependencies_use_exact_carrier_map_and_exclude_unselected(prepared):
    root, caller, payload, saved = prepared
    result = D.prepare(root, caller, payload)
    run = D.read(root, caller, result['read']['request'])
    assert run['prepared_dependencies'] == {'status': 'AVAILABLE', 'source': 'project_work.dispatch_view',
        'edges': [{'prerequisite_step_id': '0builder', 'dependent_step_id': 'Review'}]}
    assert {step['step_id'] for step in run['steps']} == {'0builder', 'Review'}
    assert all(step['state'] == 'NOT_STARTED' and 'conversation' not in step for step in run['steps'])
    assert run['definition_read']['request']['version'] == saved['version']
    (root / 'topology-owner-proof.json').write_text(json.dumps({'run': run}, indent=2))


@pytest.mark.parametrize('fault', ['absent', 'missing-packet', 'foreign-packet', 'foreign-endpoint',
                                  'non-list', 'duplicate-endpoint', 'missing-map', 'ambiguous-map', 'foreign-map'])
def test_prepared_dependencies_unavailable_without_inference_or_losing_run(prepared, monkeypatch, fault):
    root, caller, payload, _ = prepared
    result = D.prepare(root, caller, payload)
    original_view, original_checked = W.dispatch_view, A._checked
    def view(*args, **kwargs):
        observed = copy.deepcopy(original_view(*args, **kwargs))
        relation = observed['dependencies']
        worker, judge = list(relation)
        if fault == 'absent': observed.pop('dependencies')
        elif fault == 'missing-packet': relation.pop(worker)
        elif fault == 'foreign-packet': relation['foreign-packet'] = []
        elif fault == 'foreign-endpoint': relation[judge] = ['foreign-packet']
        elif fault == 'non-list': relation[judge] = worker
        elif fault == 'duplicate-endpoint': relation[judge] = [worker, worker]
        return observed
    def checked(*args, **kwargs):
        plan, pin, artifact = original_checked(*args, **kwargs)
        pin = copy.deepcopy(pin)
        if fault == 'missing-map': pin['step_packets'].pop('Review')
        elif fault == 'ambiguous-map': pin['step_packets']['Review'] = pin['step_packets']['0builder']
        elif fault == 'foreign-map': pin['step_packets']['synthesis'] = 'foreign-packet'
        return plan, pin, artifact
    monkeypatch.setattr(W, 'dispatch_view', view)
    monkeypatch.setattr(A, '_checked', checked)
    run = D.read(root, caller, {**result['read']['request'], 'step_id': 'Review'})
    dependencies = run['prepared_dependencies']
    assert dependencies['status'] == 'UNAVAILABLE' and dependencies['edges'] == [] and dependencies['reason']
    assert dependencies['source'] == 'project_work.dispatch_view'
    assert run['reference'] == payload['reference'] and run['observation']['execution_state'] == 'PLANNED'
    assert run['work']['id'] == result['work']['id'] and run['step_detail']['step_id'] == 'Review'
    assert all('conversation' not in step for step in run['steps'])
    assert run['step_detail']['state'] == ('UNAVAILABLE' if fault in {'missing-map', 'ambiguous-map'} else 'NOT_STARTED')
    assert len(records.fold_records(root)['sessions']) == len(records.fold_records(root)['turns']) == 1


def test_prepared_dependencies_order_is_canonical_not_saved_or_mapping_order():
    pin = {'step_ids': ['z', 'a', 'm'], 'step_packets': {'m': 'p2', 'z': 'p0', 'a': 'p1'}}
    first = A._prepared_dependencies(pin, {'p2': ['p0', 'p1'], 'p0': [], 'p1': ['p0']})
    assert first == A._prepared_dependencies(pin, {'p1': ['p0'], 'p0': [], 'p2': ['p1', 'p0']})
    assert first['edges'] == [{'prerequisite_step_id': 'z', 'dependent_step_id': 'a'},
        {'prerequisite_step_id': 'a', 'dependent_step_id': 'm'},
        {'prerequisite_step_id': 'z', 'dependent_step_id': 'm'}]
    # Mapping-only boundary, not an admission claim: the current app carrier requires review.
    assert A._prepared_dependencies(pin, {'p0': [], 'p1': [], 'p2': []}) == {
        'status': 'AVAILABLE', 'source': 'project_work.dispatch_view', 'edges': []}


@pytest.mark.parametrize('condition', ['http', 'review', 'expired', 'foreign'])
def test_actual_preparation_admission_refuses_before_artifact_or_work(prepared, condition):
    root, caller, payload, _ = prepared
    if condition == 'http':
        caller = O.owned_workspace('http')
    elif condition == 'review':
        records.bank(root, {'record': 'writing-session', 'id': 'WS-parent', 'project': 'book', 'role': 'review'})
    elif condition == 'expired':
        records.bank(root, {'record': 'writing-reply', 'id': 'done', 'project': 'book', 'turn_id': 'prepare-turn',
                            'session_id': 'WS-parent', 'status': 'completed', 'text': 'Finished'})
    else:
        foreign = D.save(root, O.owned_workspace('sdk'), {'request_id': 'foreign', 'expected_revision': None,
            'scope': {'kind': 'owned-workspace'}, 'definition': copy.deepcopy(BODY)})
        payload = {**payload, 'reference': foreign['reference']}
    with pytest.raises(D.Refused):
        D.prepare(root, caller, payload)
    assert not W._tasks('book', root)
    assert not [row for row in records.index(root).by_project['book'] if row['record'] == 'writing-artifact']


def test_preparation_rechecks_actual_admission_after_waiting_for_lock(prepared, monkeypatch):
    root, caller, payload, _ = prepared
    original = W.dispatch_lock
    @contextmanager
    def delayed(root):
        with original(root):
            records.bank(root, {'record': 'writing-reply', 'id': 'done', 'project': 'book', 'turn_id': 'prepare-turn',
                                'session_id': 'WS-parent', 'status': 'completed', 'text': 'Ended while waiting'})
            yield
    monkeypatch.setattr(W, 'dispatch_lock', delayed)
    with pytest.raises(D.Refused, match='NATIVE_WRITE_NOT_ADMITTED'):
        D.prepare(root, caller, payload)
    assert not W._tasks('book', root)
    assert not [row for row in records.index(root).by_project['book'] if row['record'] == 'writing-artifact']


@pytest.mark.parametrize('mutation', ['edge', 'input', 'settings'])
def test_unconsumed_selected_semantics_never_land_effects(prepared, mutation):
    root, caller, payload, saved = prepared
    body = copy.deepcopy(BODY)
    if mutation == 'edge':
        body['edges'][0]['kind'] = 'feedback'
    elif mutation == 'input':
        body['steps'][0]['inputs'] = ['A promised binding']
    else:
        body['steps'][0]['assignment']['settings'] = {'input_policy': 'write-anywhere'}
    changed = D.save(root, O.project_scope('book', 'sdk'), {'request_id': 'new-unsupported',
        'definition_id': saved['definition_id'], 'expected_revision': saved['version'], 'definition': body})
    with pytest.raises(D.Refused, match='UNSUPPORTED_APP_SLICE') as failure:
        D.prepare(root, caller, {**payload, 'reference': changed['reference']})
    assert failure.value.details['obligations'] and not W._tasks('book', root)


def test_existing_foreign_or_changed_plan_is_not_overwritten(prepared):
    root, caller, payload, _ = prepared
    ident, relative = A._keys('book', payload['request_id'])
    path = artifacts.resolve_path(root, 'book', relative); path.parent.mkdir(parents=True)
    path.write_text('foreign bytes')
    with pytest.raises(D.Refused, match='APP_PREPARATION_UNAVAILABLE'):
        D.prepare(root, caller, payload)
    assert path.read_text() == 'foreign bytes' and not W._tasks('book', root)


def test_deferred_start_keeps_original_session_and_rechecks_current_turn(prepared):
    root, caller, payload, _ = prepared
    result = D.prepare(root, caller, payload)
    work = W._tasks('book', root)[result['work']['id']]
    records.bank(root, {'record': 'writing-reply', 'id': 'done', 'project': 'book', 'turn_id': 'prepare-turn',
                        'session_id': 'WS-parent', 'status': 'completed', 'text': 'Prepared only'})
    records.bank(root, {'record': 'writing-turn', 'id': 'later-turn', 'session_id': 'WS-parent', 'project': 'book', 'mode': 'work'})
    child_hosts._update_child_execution(root, 'WS-parent', {'turn_id': 'later-turn'})
    A.admit_launch(root, 'book', work, 'later-turn')
    records.bank(root, {'record': 'writing-session', 'id': 'WS-other', 'project': 'book', 'role': 'author'})
    records.bank(root, {'record': 'writing-turn', 'id': 'foreign-turn', 'session_id': 'WS-other', 'project': 'book', 'mode': 'work'})
    child_hosts._begin_child_execution(root, 'WS-other', {'state': 'RUNNING', 'turn_id': 'foreign-turn',
        'project': 'book', 'session_id': 'WS-other', 'host': child_hosts._process_identity()})
    with pytest.raises(D.Refused, match='ORIGINAL_PARENT_SESSION_REQUIRED'):
        A.admit_launch(root, 'book', work, 'foreign-turn')
    records.bank(root, {'record': 'writing-reply', 'id': 'later-done', 'project': 'book', 'turn_id': 'later-turn',
                        'session_id': 'WS-parent', 'status': 'completed', 'text': 'Finished'})
    with pytest.raises(D.Refused, match='NATIVE_WRITE_NOT_ADMITTED'):
        A.admit_launch(root, 'book', work, 'later-turn')
    assert not W._tasks('book', root)[work['id']].get('dispatch_admitted')


def test_run_step_joins_only_actual_recorded_packet_and_public_content(prepared):
    root, caller, payload, saved = prepared
    result = D.prepare(root, caller, payload)
    packet = result['run']['step_packets']['0builder']
    records.bank(root, {'record': 'writing-session', 'id': 'WS-recordedchild', 'project': 'book',
        'role': 'author', 'dispatch_id': result['work']['id'], 'packet': packet})
    records.bank(root, {'record': 'writing-turn', 'id': 'recorded-child', 'session_id': 'WS-recordedchild',
        'project': 'book', 'mode': 'work', 'dispatch_id': result['work']['id'], 'text': 'Public child request'})
    records.bank(root, {'record': 'writing-reply', 'id': 'recorded-result', 'session_id': 'WS-recordedchild',
        'project': 'book', 'turn_id': 'recorded-child', 'status': 'completed', 'text': 'Complete public result. ' * 1000})
    run = D.read(root, caller, {**result['read']['request'], 'step_id': '0builder'})
    detail = run['step_detail']
    assert detail['session_id'] == 'WS-recordedchild' and detail['turn_id'] == 'recorded-child'
    assert 'project=book' in detail['conversation']['session_read']['http']['url']
    assert 'view=turn' in detail['conversation']['public_content_read']['http']['url']
    assert detail['typed_return_read']['availability'] == 'UNAVAILABLE'
    assert run['steps'][1]['binding']['status'] == 'UNAVAILABLE'
    assert run['observation']['review_state'] == 'PENDING'
    from urllib.parse import urlsplit, parse_qs
    from laplace.web import authoring_http
    handle = detail['conversation']['public_content_read']['http']
    address = urlsplit(handle['url'])
    code, _, raw = authoring_http.handle(root, address.path, parse_qs(address.query), 'GET', b'')
    assert code == 200 and json.loads(raw)['turn']['reply']['text'] == 'Complete public result. ' * 1000
    # Invalid typed returns remain inspectable public evidence, not accepted completion.
    _, relative = A._keys('book', payload['request_id'])
    plan = json.loads(artifacts.resolve_path(root, 'book', relative).read_text())
    returned = artifacts.resolve_path(root, 'book', plan['packets'][0]['return_path'])
    returned.write_text('{"schema_version":"laplace.packet-return/2","status":"BLOCKED"}')
    refreshed = D.read(root, caller, {**result['read']['request'], 'step_id': '0builder'})['step_detail']
    assert refreshed['return_errors'] and refreshed['typed_return_read']['availability'] == 'OBSERVED'
    from laplace.web import research_surface
    address = urlsplit(refreshed['typed_return_read']['http']['url'])
    code, _, raw = research_surface.handle(address.path, parse_qs(address.query), 'GET', b'', repo_root=root)
    assert code == 200 and raw


def test_prepared_effect_keeps_exact_receipt_when_run_projection_fails(prepared, monkeypatch):
    root, caller, payload, _ = prepared
    monkeypatch.setattr(A, 'run', lambda *a, **k: (_ for _ in ()).throw(OSError('Projection unavailable')))
    result = D.prepare(root, caller, payload)
    projected = D.native_change_projection(result)
    assert projected['effect'] == 'prepared' and projected['receipt'] and projected['work']['id'] and projected['plan']['id']
    assert projected['parent']['prepared_by']['session_id'] == 'WS-parent'
    assert projected['observation']['status'] == 'UNAVAILABLE'
    assert projected['next_read'] == result['read']['native']


def test_parent_work_join_recovers_without_duplicate_work_or_artifact(prepared, monkeypatch):
    root, caller, payload, _ = prepared
    W.task('book', {'id': 'parent', 'title': 'Actual containing Work', 'goal': 'Complete reviewed work'}, root)
    records.bank(root, {'record': 'writing-turn', 'id': 'parent-prepare', 'session_id': 'WS-parent',
                        'project': 'book', 'mode': 'work', 'work_id': 'parent'})
    child_hosts._update_child_execution(root, 'WS-parent', {'turn_id': 'parent-prepare'})
    caller = D.native_caller(root, 'book', 'work', 'parent-prepare')
    from laplace.writing import tool_work
    original = tool_work.join_dispatch_parent
    monkeypatch.setattr(tool_work, 'join_dispatch_parent', lambda *a: (_ for _ in ()).throw(OSError('Parent join interrupted')))
    with pytest.raises(D.Refused, match='APP_PREPARATION_PARTIAL'):
        D.prepare(root, caller, payload)
    partial = D.read(root, caller, {'facet': 'request', 'request_id': payload['request_id']})
    assert partial['effect'] == 'partial' and partial['status'] == 'PARTIAL'
    monkeypatch.setattr(tool_work, 'join_dispatch_parent', original)
    result = D.prepare(root, caller, payload)
    tasks = W._tasks('book', root)
    assert tasks[result['work']['id']]['parent_work_id'] == 'parent'
    assert tasks['parent']['depends_on'] == [result['work']['id']]
    assert len(tasks) == 2
    assert len([row for row in records.index(root).by_project['book'] if row['record'] == 'writing-artifact']) == 1


def test_http_composer_read_uses_owner_typed_inputs_and_starts_nothing(prepared):
    root, _, payload, saved = prepared
    handle = D.handle(saved['definition_id'], saved['version'], facet='app-compose',
        **{key: payload[key] for key in ('request_id', 'step_ids', 'goal', 'fan_out_max')})
    from urllib.parse import urlsplit, parse_qs
    from laplace.web import workflow_definitions_surface
    address = urlsplit(handle['http']['url'])
    code, _, raw = workflow_definitions_surface.handle(address.path, parse_qs(address.query), 'GET', repo_root=root)
    assert code == 200
    result = json.loads(raw)
    assert result['prepare_payload'] == {'action': 'prepare', **payload}
    assert result['action']['payload']['project'] == 'book' and result['action']['send_required']
    assert len(records.fold_records(root)['turns']) == 1 and not W._tasks('book', root)


def test_launch_rechecks_effect_admission_after_settings_validation(prepared, monkeypatch):
    root, caller, payload, _ = prepared
    result = D.prepare(root, caller, payload)
    from laplace.writing import dispatch_execution
    original = W.validate_session_settings
    changed = [False]
    def expires(*a, **k):
        value = original(*a, **k)
        if not changed[0]:
            records.bank(root, {'record': 'writing-reply', 'id': 'done', 'project': 'book', 'turn_id': 'prepare-turn',
                                'session_id': 'WS-parent', 'status': 'completed', 'text': 'Ended during validation'})
            changed[0] = True
        return value
    monkeypatch.setattr(W, 'validate_session_settings', expires)
    monkeypatch.setattr(dispatch_execution, '_start_dispatch_children', lambda *a: pytest.fail('Child start after expired admission'))
    with pytest.raises(D.Refused, match='NATIVE_WRITE_NOT_ADMITTED'):
        dispatch_execution.launch_dispatch(root, 'book', 'prepare-turn', {'id': result['work']['id']})
    assert not W._tasks('book', root)[result['work']['id']].get('dispatch_admitted')


@pytest.mark.parametrize('reservation', ['completed', 'partial'])
def test_owned_http_save_and_import_cannot_shadow_app_request(prepared, monkeypatch, reservation):
    root, caller, payload, _ = prepared
    if reservation == 'partial':
        with monkeypatch.context() as patch:
            patch.setattr(W, 'task', lambda *a, **k: (_ for _ in ()).throw(OSError('Work interrupted')))
            with pytest.raises(D.Refused, match='APP_PREPARATION_PARTIAL'):
                D.prepare(root, caller, payload)
    else:
        D.prepare(root, caller, payload)
    expected = D.read(root, caller, {'facet': 'request', 'request_id': payload['request_id']})
    from laplace.web import workflow_definitions_surface
    before = (root / D.W.LEDGER).read_bytes()
    code, _, raw = workflow_definitions_surface.handle('/work/workflow-definitions/save', {}, 'POST',
        json.dumps({'request_id': payload['request_id'], 'expected_revision': None, 'definition': BODY}).encode(), repo_root=root)
    assert code == 409 and json.loads(raw)['code'] == 'REQUEST_CONFLICT'
    legacy = {'profile': D.W.SPEC_SCHEMA, 'request_id': payload['request_id'], 'reference': payload['reference'],
        'selected_steps': ['0builder', 'Review', 'synthesis'], 'node': 'synthetic', 'goal': 'A different carrier', 'write_paths': []}
    with pytest.raises(D.Refused, match='REQUEST_CONFLICT'):
        D.prepare(root, O.owned_workspace('sdk'), legacy)
    other = root / 'foreign-transfer-source'; other.mkdir()
    foreign = D.save(other, O.owned_workspace('sdk'), {'request_id': payload['request_id'],
        'expected_revision': None, 'definition': copy.deepcopy(BODY)})
    package = D.read(other, O.owned_workspace('sdk'), {'reference': foreign['reference'], 'facet': 'export'})
    with pytest.raises(D.Refused, match='RESTORE_REQUEST_CONFLICT'):
        D.restore(root, O.owned_workspace('sdk'), package)
    observed = D.read(root, O.owned_workspace('http'), {'facet': 'request', 'request_id': payload['request_id']})
    assert observed['effect'] == expected['effect']
    assert observed.get('receipt', observed.get('artifact')) == expected.get('receipt', expected.get('artifact'))
    assert (root / D.W.LEDGER).read_bytes() == before


def test_contradictory_historical_request_reports_both_scoped_receipts(prepared):
    root, caller, payload, _ = prepared
    app = D.prepare(root, caller, payload)
    other = root / 'historical-source'; other.mkdir()
    prior = D.save(other, O.owned_workspace('sdk'), {'request_id': payload['request_id'],
        'expected_revision': None, 'definition': copy.deepcopy(BODY)})
    package = D.read(other, O.owned_workspace('sdk'), {'reference': prior['reference'], 'facet': 'export'})
    # Synthetic historical contradiction from the old HTTP gap, not an admitted new import.
    row, body = package['versions'][0]['row'], package['versions'][0]['definition']
    D.writing_bodies.store(root).put(D.W.canonical(body)); D.W._bank(root, row)
    observed = D.read(root, O.owned_workspace('http'), {'facet': 'request', 'request_id': payload['request_id']})
    assert observed['status'] == 'AMBIGUOUS' and observed['effect'] == 'unknown'
    receipts = [match.get('receipt') for match in observed['matches']]
    assert app['receipt'] in receipts and prior['receipt'] in receipts
    native = D.read(root, caller, {'facet': 'request', 'request_id': payload['request_id']})
    assert native['effect'] == 'prepared' and native['receipt'] == app['receipt']
