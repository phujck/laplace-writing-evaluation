"""Actual read adapters over public records; metadata service/processes forbidden."""
import json
import socket
import subprocess

import pytest
import runtime_guard

from laplace.writing import records, provider, provider_catalogue as C, tool_sessions, session_reads, dispatch_execution, dispatch_parent
from laplace.native import tools, declarations
from laplace.projects import artifacts
from laplace.work import project_work


@pytest.fixture
def passive(tmp_path, monkeypatch, register_project):
    runtime_guard.arm(monkeypatch)
    monkeypatch.delenv('LAPLACE_CUSTODY_LIVE', raising=False)
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'empty-codex-home'))
    register_project(tmp_path, 'book')
    forbidden = lambda *a, **k: pytest.fail('Passive read reached provider/process/network discovery')
    monkeypatch.setattr(provider, 'capabilities', forbidden)
    monkeypatch.setattr(provider, '_claude_models', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(C, '_live_memory', lambda *a: None)
    records.bank(tmp_path, {'record': 'writing-session', 'id': 'WS-reader', 'project': 'book',
        'provider': 'codex', 'model': 'fixture-model', 'effort': 'low', 'role': 'author'})
    budget = dispatch_parent.observation_budget(31)
    records.bank(tmp_path, {'record': 'writing-turn', 'id': 'WT-reader', 'session_id': 'WS-reader',
        'project': 'book', 'mode': 'work', 'connected_observation': budget, 'text': 'Public body. ' * 5000})
    path = C._catalogue_path(tmp_path);path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'schema_version': 'laplace.provider-catalogue/1', 'observed_at': 100,
        'updated_at': 200, 'observation_scope': {'kind': 'provider', 'provider_id': 'codex'},
        'providers': [{'id': 'codex', 'available': True, 'observed_at': 200, 'model_observed_at': 190,
                      'models': [{'id': 'fixture-model', 'efforts': ['low']}]}]}))
    return tmp_path, budget


@pytest.mark.parametrize('known', [True, False])
def test_real_native_summary_is_passive_and_qualifies_known_or_unknown_catalogue(passive, monkeypatch, known):
    root, budget = passive
    if not known:
        C._catalogue_path(root).unlink()
        monkeypatch.setattr(C.shutil, 'which', lambda *a: None)
    result = tools.execute(root, 'book', 'work', 'session_settings', {}, turn_id='WT-reader')
    assert result['session']['id'] == 'WS-reader' and result['connected_observation'] == budget
    assert result['provider_observation']['mode'] == 'passive'
    assert result['provider_observation']['observed_at'] == (100 if known else None)
    if known:
        assert result['provider_observation']['updated_at'] == 200
        assert result['provider_observation']['observation_scope'] == {'kind': 'provider', 'provider_id': 'codex'}
        assert result['providers'][0]['model_observed_at'] == 190
    else:
        assert {row['id'] for row in result['providers']} == {'codex', 'claude'}
        assert all(row['auth_state'] == 'UNVERIFIED' for row in result['providers'])


def test_connection_reads_exact_admitted_fields_without_catalogue_body_or_child_schema(passive, monkeypatch):
    root, budget = passive
    forbidden = lambda *a, **k: pytest.fail('Connection view expanded unrelated read context')
    monkeypatch.setattr(C, 'provider_catalogue', forbidden)
    monkeypatch.setattr(session_reads, 'session_state', forbidden)
    monkeypatch.setattr(dispatch_execution, '_child_return_contract', forbidden)
    index = records.index(root);before = index.stats.get('custody_bodies_opened', 0)
    result = tool_sessions.session_settings(root, 'book', {'view': 'connection'}, 'WT-reader')
    assert result == {'caller_turn_id': 'WT-reader', 'session_id': 'WS-reader', 'project': 'book', 'connected_observation': budget}
    assert records.index(root).stats.get('custody_bodies_opened', 0) == before
    native = tools.execute(root, 'book', 'work', 'session_settings', {'view': 'connection'}, turn_id='WT-reader')
    assert native['connected_observation'] == budget and native['caller_turn_id'] == 'WT-reader'
    assert 'providers' not in native and 'return_contract' not in native and 'session' not in native
    public = tools.call(root, 'book', 'work', {'operation': 'session_settings', 'payload': {'view': 'connection'}}, turn_id='WT-reader')
    assert public['caller_turn_id'] == 'WT-reader' and public['connected_observation'] == budget
    assert 'connection' in declarations.DECLARATIONS['session_settings'].payload['properties']['view']['enum']
    (root / 'connection-proof.json').write_text(json.dumps({'direct': result, 'native': native, 'public': public,
        'direct_custody_body_expansion': 0, 'provider_discovery': 'forbidden', 'process_network': 'forbidden'}, indent=2))


@pytest.mark.parametrize('project,turn', [('other', 'WT-reader'), ('book', None), ('book', 'missing')])
def test_connection_preserves_actual_caller_project_scope(passive, project, turn):
    root, _ = passive
    with pytest.raises(ValueError, match='current logical turn'):
        tools.execute(root, project, 'work', 'session_settings', {'view': 'connection'}, turn_id=turn)


def test_real_child_return_contract_and_schema_stay_passive_and_scoped(passive):
    root, _ = passive
    plan = {'schema_version': 'laplace.dispatch-plan/1', 'fan_out_max': 2, 'packets': [
        {'packet': 'worker', 'role': 'worker', 'brief': 'Write a public report.', 'return_path': 'development/worker.json'},
        {'packet': 'review', 'role': 'judge', 'brief': 'Review it independently.', 'return_path': 'development/review.json'}]}
    stored = artifacts.store(root, 'book', {'path': 'development/plan.json', 'scope': 'project', 'before': None, 'content': json.dumps(plan)})
    project_work.task('book', {'id': 'dispatch', 'title': 'Public dispatch', 'goal': 'Reviewed result',
        'kind': 'dispatch', 'evidence': [stored['path']]}, root)
    records.bank(root, {'record': 'writing-session', 'id': 'WS-review', 'project': 'book', 'role': 'review',
        'dispatch_id': 'dispatch', 'packet': 'review', 'provider': 'codex'})
    records.bank(root, {'record': 'writing-turn', 'id': 'WT-review', 'session_id': 'WS-review', 'project': 'book',
        'dispatch_id': 'dispatch', 'parent_turn_id': 'WT-reader', 'mode': 'review'})
    contract = tools.execute(root, 'book', 'review', 'session_settings', {'view': 'return-contract'}, turn_id='WT-review')
    schema = tools.execute(root, 'book', 'review', 'session_settings', {'view': 'return-schema'}, turn_id='WT-review')
    assert contract['return_contract']['own_packet'] == 'review'
    assert contract['return_contract']['schema_id'] == schema['schema_id'] == 'laplace.packet-judgement/2'
    assert schema['schema']['$id'] == schema['schema_id']
    assert contract['return_contract']['publish_action']['operation'] == 'store_artifact'
    assert 'providers' not in schema and 'providers' not in contract


def test_explicit_refresh_and_selected_validation_keep_their_active_roles(passive, monkeypatch):
    root, _ = passive
    calls = []
    catalogue = {'providers': [{'id': 'codex', 'available': True, 'models': [
        {'id': 'fixture-model', 'default_effort': 'low', 'efforts': ['low']}]}]}
    def active(path, refresh=False, **kwargs):
        calls.append((path, refresh, kwargs));return catalogue
    monkeypatch.setattr(provider, 'capabilities', active)
    from laplace.web import authoring_http
    code, _, raw = authoring_http.handle(root, '/authoring/providers', {'refresh': ['1']}, 'GET', b'')
    assert code == 200 and json.loads(raw)['providers'][0]['id'] == 'codex'
    assert calls == [(root, True, {})]
    calls.clear()
    choice = project_work.validate_session_settings({'provider': 'codex', 'model': 'fixture-model', 'effort': 'low'}, root)
    assert choice['effort'] == 'low' and calls == [(root, False, {'provider_id': 'codex'})]
