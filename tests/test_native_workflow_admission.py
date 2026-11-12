"""Deterministic admitted host, actual native dispatch and existing owner; no provider invocation."""
from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import asdict
import json

import pytest
import runtime_guard

from laplace.pipeline import workflow_definitions as D
from laplace.work import owner_discovery as O
from laplace.writing import records, child_hosts
from laplace.native import tools, declarations, verbs


BODY = {'schema_version': D.SCHEMA, 'title': 'An admitted workflow', 'description': 'Full role text survives.',
        'settings': {}, 'layout': {}, 'steps': [{'id': 'author', 'title': 'Author', 'parent_id': None,
        'assignment': {'role': 'builder', 'instructions': 'Complete instructions.\n' + 'Retained paragraph. ' * 300,
                       'settings': {}}}], 'edges': []}


@pytest.fixture
def admitted(tmp_path, monkeypatch, register_project):
    runtime_guard.arm(monkeypatch)
    monkeypatch.delenv('LAPLACE_CUSTODY_LIVE', raising=False)
    register_project(tmp_path, 'book')
    cache = tmp_path / '.laplace-cache'; cache.mkdir(exist_ok=True)
    (cache / 'writing-provider-catalogue.json').write_text(json.dumps({'schema_version': 'laplace.provider-catalogue/1',
        'observed_at': 99999999999, 'providers': [{'id': 'codex', 'available': False, 'models': []}]}))
    records.bank(tmp_path, {'record': 'writing-session', 'id': 'WS-fixture', 'project': 'book', 'role': 'author',
                           'provider': 'codex', 'model': 'fixture', 'effort': 'medium'})
    records.bank(tmp_path, {'record': 'writing-turn', 'id': 'turn', 'session_id': 'WS-fixture', 'project': 'book',
                           'mode': 'discuss', 'text': 'Save my reusable workflow', 'context_parts': []})
    child_hosts._begin_child_execution(tmp_path, 'WS-fixture', {'state': 'RUNNING', 'turn_id': 'turn',
        'session_id': 'WS-fixture', 'project': 'book', 'host': child_hosts._process_identity(),
        'provider_process': None, 'provider_processes': []})
    return tmp_path


def native(root, payload, *, turn='turn', mode='discuss', project='book'):
    return tools.execute(root, project, mode, 'workflow_definition_change', payload, turn_id=turn)


def create_payload(rid='create'):
    return {'action': 'save', 'request_id': rid, 'expected_revision': None, 'definition': copy.deepcopy(BODY)}


def definitions(root):
    return [row for row in D._rows(root)]


def test_actual_native_save_read_update_replay_and_stale(admitted):
    root = admitted
    listing = tools.execute(root, 'book', 'discuss', 'project', {'view': 'workflow-definitions'}, turn_id='turn')
    action = listing['actions']['create']
    assert action['available'] and action['permitted'] and action['native']['operation'] == 'workflow_definition_change'
    first = native(root, {**action['native']['payload'], 'request_id': 'create', 'definition': copy.deepcopy(BODY)})
    assert first['effect'] == 'saved' and first['scope'] == {'kind': 'project', 'namespace': 'book'}
    ident, v1 = first['definition_id'], first['version']
    sdk = D.read(root, O.owned_workspace('sdk'), first['read']['request'])
    assert sdk['definition'] == BODY and sdk['version'] == v1
    read = tools.execute(root, 'book', 'discuss', 'project', first['read']['native']['payload'], turn_id='turn')
    assert read['definition'] == BODY and read['permissions']['save'] and not read['permissions']['prepare']
    assert not read['actions']['prepare']['available']
    update = {**read['actions']['save']['native']['payload'], 'request_id': 'update', 'definition': copy.deepcopy(BODY)}
    update['definition']['title'] = 'Saved again'
    second = native(root, update)
    assert second['effect'] == 'saved' and second['version'] != v1
    replay = native(root, create_payload())
    assert replay['replayed'] and replay['receipt'] == first['receipt'] and replay['version'] == v1
    with pytest.raises(D.Refused, match='STALE_EDIT') as stale:
        native(root, {**update, 'request_id': 'stale', 'expected_revision': v1})
    assert stale.value.details['current_read_handle']['request'] == {'definition_id': ident}
    historical = tools.execute(root, 'book', 'discuss', 'project', first['read']['native']['payload'], turn_id='turn')
    assert historical['version'] == historical['edit_revision'] == v1
    assert historical['head_revision'] == second['version'] and not historical['is_current']
    assert historical['actions']['save']['native']['payload']['expected_revision'] == v1
    assert len(definitions(root)) == 2 and not list((root / 'evidence' / 'WORKFLOWS').glob('*/run.json'))
    (root / 'native-proof.json').write_text(json.dumps({'simulation': 'Deterministic admitted session/turn and real current process host; no provider',
        'create': first, 'sdk_exact_read': sdk, 'native_exact_read': read, 'update': second,
        'original_request_replay': replay, 'historical': historical, 'stale_refusal': stale.value.details,
        'definition_records': len(definitions(root)), 'prepared_runs': 0}, indent=2))


@pytest.mark.parametrize('extra', [{'project': 'other'}, {'role': 'author'}, {'admission': True}, {'turn_id': 'turn'}])
def test_payload_cannot_supply_authority(admitted, extra):
    with pytest.raises(ValueError):
        native(admitted, {**create_payload(), **extra})
    assert not definitions(admitted)


@pytest.mark.parametrize('scope', [{'kind': 'owned-workspace'}, {'kind': 'project', 'namespace': 'other'}])
def test_foreign_and_workspace_custody_refused(admitted, scope):
    with pytest.raises(D.Refused, match='NOT_IN_SCOPE'):
        native(admitted, {**create_payload(), 'scope': scope})
    foreign = D.save(admitted, O.owned_workspace('sdk'), {'request_id': 'foreign', 'expected_revision': None,
                    'scope': scope, 'definition': copy.deepcopy(BODY)})
    with pytest.raises(D.Refused, match='NOT_IN_SCOPE'):
        native(admitted, {**create_payload('foreign-update'), 'definition_id': foreign['definition_id'],
                          'expected_revision': foreign['version']})
    assert len(definitions(admitted)) == 1


@pytest.mark.parametrize('condition', ['unadmitted', 'finished', 'unattributed', 'review-role', 'wrong-mode', 'dead-host'])
def test_actual_admission_controls(admitted, condition):
    turn = 'turn'; mode = 'discuss'
    if condition == 'unadmitted': turn = 'missing'
    elif condition == 'finished':
        records.bank(admitted, {'record': 'writing-reply', 'id': 'reply', 'project': 'book', 'turn_id': 'turn',
                               'session_id': 'WS-fixture', 'status': 'completed', 'text': 'Finished'})
    elif condition == 'review-role':
        records.bank(admitted, {'record': 'writing-session', 'id': 'WS-fixture', 'project': 'book', 'role': 'review'})
    elif condition == 'wrong-mode': mode = 'work'
    else:
        child_hosts._update_child_execution(admitted, 'WS-fixture',
            {'turn_id': 'another'} if condition == 'unattributed' else {'host': {'pid': 999999999, 'created_at': 0}})
    read = tools.execute(admitted, 'book', mode, 'project', {'view': 'workflow-definitions'}, turn_id=turn)
    assert read['actions']['create']['available'] and not read['actions']['create']['permitted']
    with pytest.raises(D.Refused, match='NATIVE_WRITE_NOT_ADMITTED'):
        native(admitted, create_payload(), turn=turn, mode=mode)
    assert not definitions(admitted)


def test_coarse_read_and_review_mode_are_truthful(admitted):
    coarse = D.read(admitted, O.project_scope('book', 'native'))
    assert coarse['actions']['create']['available'] and not coarse['actions']['create']['permitted']
    assert coarse['actions']['create']['admission']['code'] == 'NATIVE_ADMISSION_REQUIRED'
    with pytest.raises(ValueError, match='Independent review'):
        native(admitted, create_payload(), mode='review')
    assert not definitions(admitted)


def test_rechecks_admission_after_writer_lock(admitted, monkeypatch):
    original = D._lock
    @contextmanager
    def delayed(root):
        with original(root):
            records.bank(root, {'record': 'writing-reply', 'id': 'reply', 'project': 'book', 'turn_id': 'turn',
                               'session_id': 'WS-fixture', 'status': 'completed', 'text': 'Finished while waiting'})
            yield
    monkeypatch.setattr(D, '_lock', delayed)
    with pytest.raises(D.Refused, match='NATIVE_WRITE_NOT_ADMITTED'):
        native(admitted, create_payload())
    assert not definitions(admitted)


def test_saved_effect_retained_and_lost_reply_recovered(admitted, monkeypatch):
    original = D._view
    monkeypatch.setattr(D, '_view', lambda *a: (_ for _ in ()).throw(OSError('fixture readback unavailable')))
    saved = native(admitted, create_payload())
    assert saved['effect'] == 'saved' and saved['receipt'] and saved['scope']['namespace'] == 'book'
    assert saved['observation']['status'] == 'UNAVAILABLE'
    monkeypatch.setattr(D, '_view', original)
    # The transport lost the above response. Inspection, with the original request identity, performs no replay.
    recovered = tools.execute(admitted, 'book', 'discuss', 'project',
        {'view': 'workflow-definitions', 'request': {'facet': 'request', 'request_id': 'create'}}, turn_id='turn')
    assert recovered['effect'] == 'saved' and recovered['receipt'] == saved['receipt']
    assert recovered['definition'] == BODY and len(definitions(admitted)) == 1
    (admitted / 'recovery-proof.json').write_text(json.dumps({'saved_unavailable_readback': saved,
        'request_inspection': recovered, 'definition_records': 1, 'automatic_replay': False}, indent=2))


def test_owner_schema_and_generated_semantic_route(admitted):
    assert declarations.DECLARATIONS['workflow_definition_change'].payload == D.native_change_contract()
    payload = create_payload('semantic')
    act = verbs.classify('workflow_definition_change', payload, project='book', root=admitted)
    assert act.exact and act.owner_call == ('workflow_definition_change', payload)
    request = json.loads(json.dumps(asdict(act.request)))
    assert request['payload']['definition_edit_guard'] is None
    assembled = tools.call(admitted, 'book', 'discuss', request, turn_id='turn')
    result = assembled['owner_response']
    assert result['effect'] == 'saved'
    first = result
    public = tools.call(admitted, 'book', 'discuss', {'operation': 'workflow_definition_change', 'payload': payload}, turn_id='turn')
    assert public['receipt'] == first['receipt'] and public['replayed']
    update = {**create_payload('semantic-update'), 'definition_id': first['definition_id'], 'expected_revision': first['version']}
    update['definition']['title'] = 'Semantic updated'
    current = native(admitted, update)
    stale = json.loads(json.dumps(asdict(verbs.classify('workflow_definition_change', {**update, 'request_id': 'semantic-stale'}, project='book', root=admitted).request)))
    refused = tools.call(admitted, 'book', 'discuss', stale, turn_id='turn')
    assert refused['code'] == 'STALE_EDIT'
    assert refused['current_read_handle']['request'] == {'definition_id': first['definition_id']}
    assert len(definitions(admitted)) == 2
    (admitted / 'semantic-proof.json').write_text(json.dumps({'request': request, 'saved': first,
        'stale_request': stale, 'stale_refusal': refused, 'public_expected_revision_replay': public,
        'assembled_semantic_reply': assembled, 'assembled_saved_bytes': len(__import__('laplace.projects.writing_sources', fromlist=['content_text']).content_text(assembled).encode())}, indent=2))
