"""Selected metadata/clock fixtures; no actual provider discovery, login or inference."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
import runtime_guard

from laplace.writing import provider as P, provider_catalogue as C, turn_admission, records


@pytest.fixture
def metadata(tmp_path, monkeypatch):
    runtime_guard.arm(monkeypatch)
    monkeypatch.delenv('LAPLACE_CUSTODY_LIVE', raising=False)
    monkeypatch.setattr(P, '_CAP_CACHE', None)
    monkeypatch.setattr(P, '_CAP_CACHE_ROOT', None)
    clock = [10_000.0]
    monkeypatch.setattr(P.time, 'time', lambda: clock[0])
    monkeypatch.setattr(P.shutil, 'which', lambda name: '/fixture/' + name)
    monkeypatch.setattr(P.subprocess, 'run', lambda *a, **k: pytest.fail('unselected metadata subprocess'))
    from laplace.writing import operating
    monkeypatch.setattr(operating, 'session_workspace', lambda *_: tmp_path)
    calls = []
    class Connection:
        def __init__(self, cwd, **kwargs): calls.append(('codex', str(cwd), kwargs))
        def request(self, method, payload):
            assert method == 'model/list' and payload == {'limit': 100}
            return {'data': [{'model': 'fixture-model', 'isDefault': True,
                             'supportedReasoningEfforts': [{'reasoningEffort': 'low'}]}]}
        def close(self): calls.append(('closed',))
    monkeypatch.setattr(P, 'CodexConnection', Connection)
    return tmp_path, clock, calls


def claude_metadata(monkeypatch, calls):
    def run(argv, **kwargs):
        assert argv == ['claude', 'auth', 'status', '--json']
        calls.append(('claude-auth',))
        return SimpleNamespace(stdout='{"loggedIn":true}')
    def models(cwd, **kwargs):
        calls.append(('claude-models',))
        return [{'id': 'fixture-model', 'supports_effort': False, 'efforts': []}]
    monkeypatch.setattr(P.subprocess, 'run', run)
    monkeypatch.setattr(P, '_claude_models', models)


def row(catalogue, ident):
    return next(r for r in catalogue['providers'] if r['id'] == ident)


def saved(root):
    return json.loads(P._catalogue_path(root).read_text())


def test_selected_codex_cold_refresh_and_cached_never_probe_claude(metadata, monkeypatch):
    root, clock, calls = metadata
    monkeypatch.setattr(P, '_claude_models', lambda *a, **k: pytest.fail('unselected Claude models'))
    callback = lambda *a: None
    result = P.capabilities(root, provider_id='codex', on_spawn=callback)
    assert [r['id'] for r in result['providers']] == ['codex']
    assert result['observed_at'] == clock[0] and result['catalogue_observed_at'] is None
    assert saved(root)['observed_at'] is None
    assert calls[0][2]['on_spawn'] is callback
    assert P.capabilities(root, provider_id='codex')['cached'] and len(calls) == 2
    clock[0] += 1
    P.capabilities(root, refresh=True, provider_id='codex')
    assert len([c for c in calls if c[0] == 'codex']) == 2
    assert not row(saved(root), 'claude')['observed_at']


def test_selected_claude_never_discovers_codex_and_full_action_discovers_both(metadata, monkeypatch):
    root, clock, calls = metadata
    original = P.CodexConnection
    monkeypatch.setattr(P, 'CodexConnection', lambda *a, **k: pytest.fail('unselected Codex'))
    claude_metadata(monkeypatch, calls)
    selected = P.capabilities(root, provider_id='claude')
    assert [r['id'] for r in selected['providers']] == ['claude']
    assert calls == [('claude-auth',), ('claude-models',)]
    monkeypatch.setattr(P, 'CodexConnection', original)
    all_providers = P.capabilities(root)
    assert {r['id'] for r in all_providers['providers']} == {'codex', 'claude'}
    assert all_providers['observation_scope'] == {'kind': 'catalogue'}
    assert all_providers['observed_at'] == clock[0]
    assert len([c for c in calls if c[0] == 'codex']) == 1
    assert len([c for c in calls if c[0] == 'claude-auth']) == 2
    assert P.capabilities(root)['cached']
    P.capabilities(root, refresh=True)
    assert len([c for c in calls if c[0] == 'codex']) == 2
    assert len([c for c in calls if c[0] == 'claude-auth']) == 3


def test_partial_refresh_retains_other_observation_and_does_not_freshen_full_catalogue(metadata, monkeypatch):
    root, clock, calls = metadata
    claude_metadata(monkeypatch, calls)
    full = P.capabilities(root)
    previous = saved(root)
    clock[0] += 500
    codex = P.capabilities(root, refresh=True, provider_id='codex')
    partial = saved(root)
    assert row(partial, 'claude') == row(previous, 'claude')
    assert partial['observed_at'] == full['observed_at'] == 10_000
    assert partial['updated_at'] == codex['observed_at'] == 10_500
    assert C.provider_catalogue(root)['observed_at'] == 10_000
    clock[0] = 10_601
    P.capabilities(root, provider_id='claude')
    assert len([c for c in calls if c[0] == 'claude-auth']) == 2, 'Codex refresh must not renew Claude TTL'
    assert row(saved(root), 'codex')['observed_at'] == 10_500
    (root / 'partial-proof.json').write_text(json.dumps({'full': previous, 'selected': codex, 'partial': partial}, indent=2))


def test_root_and_provider_cache_are_qualified(metadata, monkeypatch):
    root, clock, calls = metadata
    claude_metadata(monkeypatch, calls)
    P.capabilities(root, provider_id='codex')
    other = root / 'other-root'; other.mkdir()
    P.capabilities(other, provider_id='claude')
    assert row(saved(other), 'codex')['observed_at'] is None
    assert row(saved(root), 'claude')['observed_at'] is None
    P.capabilities(root, provider_id='codex')
    assert len([c for c in calls if c[0] == 'codex']) == 2, 'another root must never supply the cached row'


def test_failed_model_observation_retains_exact_last_good_model_time(metadata, monkeypatch):
    root, clock, calls = metadata
    claude_metadata(monkeypatch, calls)
    P.capabilities(root)
    prior = copy.deepcopy(row(saved(root), 'claude'))
    clock[0] += 10
    monkeypatch.setattr(P, '_claude_models', lambda *a, **k: (_ for _ in ()).throw(ValueError('fixture metadata unavailable')))
    failed = row(P.capabilities(root, refresh=True, provider_id='claude'), 'claude')
    assert failed['model_discovery_error'] == 'fixture metadata unavailable'
    assert failed['model_catalogue_source'] == 'last-known-good'
    assert failed['models'] == row(C.provider_catalogue(root), 'claude')['models']
    assert failed['model_observed_at'] == prior['model_observed_at'] == 10_000
    assert failed['observed_at'] == 10_010 and saved(root)['observed_at'] == 10_000
    assert all('tier' not in model for p in saved(root)['providers'] for model in p['models'])


def test_merge_after_probe_preserves_concurrently_saved_other_provider(metadata, monkeypatch):
    root, clock, calls = metadata
    original = P._codex_capabilities
    def probe(*a, **k):
        result = original(*a, **k)
        path = P._catalogue_path(root); path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'schema_version': 'laplace.provider-catalogue/1', 'observed_at': 20,
            'updated_at': 30, 'providers': [{'id': 'claude', 'models': [{'id': 'concurrent-model'}],
            'available': True, 'observed_at': 29, 'model_observed_at': 28}]}))
        return result
    monkeypatch.setattr(P, '_codex_capabilities', probe)
    P.capabilities(root, provider_id='codex')
    assert row(saved(root), 'claude')['models'][0]['id'] == 'concurrent-model'
    assert row(saved(root), 'claude')['model_observed_at'] == 28


def test_failed_persistence_does_not_hide_new_partial_memory(metadata, monkeypatch):
    root, clock, calls = metadata
    claude_metadata(monkeypatch, calls)
    P.capabilities(root)
    clock[0] += 1
    monkeypatch.setattr(P.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('fixture disk unavailable')))
    P.capabilities(root, refresh=True, provider_id='codex')
    passive = C.provider_catalogue(root)
    assert passive['updated_at'] == 10_001 and passive['observed_at'] == 10_000
    assert row(passive, 'codex')['observed_at'] == 10_001
    assert row(passive, 'claude')['observed_at'] == 10_000
    assert saved(root)['updated_at'] == 10_000


def test_unknown_provider_refuses_before_any_probe_or_cache_read(metadata, monkeypatch):
    root, _, calls = metadata
    monkeypatch.setattr(P, 'provider_catalogue', lambda *a: pytest.fail('unknown selection read catalogue'))
    with pytest.raises(P.ProviderError, match='Unknown writing provider'):
        P.capabilities(root, provider_id='unrelated')
    assert calls == [] and not P._catalogue_path(root).exists()


@pytest.mark.parametrize('provider,effort', [('codex', 'low'), ('claude', None)])
def test_effort_truth_consumes_only_session_provider_and_preserves_settings_owner(metadata, monkeypatch, provider, effort):
    root, _, calls = metadata
    if provider == 'claude':
        claude_metadata(monkeypatch, calls)
        monkeypatch.setattr(P, 'CodexConnection', lambda *a, **k: pytest.fail('unselected Codex'))
    session = {'record': 'writing-session', 'id': 'WS-fixture', 'project': 'book', 'role': 'author',
               'provider': provider, 'model': 'fixture-model', 'effort': 'low', 'settings_revision': 0}
    records.bank(root, session)
    truth = turn_admission.effort_as_sent(root, session)
    assert truth['session']['effort'] == effort and truth['supports_effort'] is (effort is not None)
    again = turn_admission.effort_as_sent(root, truth['session'])
    assert again['session']['effort'] == effort
    rows = [json.loads(line) for line in (root / 'contract/talk.jsonl').read_text().splitlines()]
    assert len([r for r in rows if r['record'] == 'writing-session-settings']) == (1 if effort is None else 0)


def test_metadata_spawn_attribution_precedes_stdin_and_refusal_cleans_process(metadata):
    root, _, _ = metadata
    # Inert Python child only. It stands in for metadata transport, not provider inference.
    observed = []
    def publish(process, phase): observed.append((process.pid, phase))
    result = P._metadata_run([sys.executable, '-I', '-c', 'import sys; print(sys.stdin.read())'],
                             input='fixture metadata', timeout=3, on_spawn=publish, phase='fixture-metadata')
    assert result.stdout.strip() == 'fixture metadata' and observed[0][1] == 'fixture-metadata'
    def refuse(process, phase):
        observed.append((process.pid, phase))
        raise OSError('fixture registration refused')
    with pytest.raises(P.ProcessRegistrationError, match='registration refused'):
        P._metadata_run([sys.executable, '-I', '-c', 'import time; time.sleep(30)'],
                         input='must not send', timeout=3, on_spawn=refuse, phase='fixture-refused')
    import psutil
    assert not psutil.pid_exists(observed[-1][0])


def test_selected_registration_refusal_does_not_probe_other_provider_or_cache_failure(metadata, monkeypatch):
    root, _, calls = metadata
    monkeypatch.setattr(P, 'CodexConnection', lambda *a, **k: (_ for _ in ()).throw(P.ProcessRegistrationError('fixture registration refused')))
    with pytest.raises(P.ProcessRegistrationError, match='registration refused'):
        P.capabilities(root, provider_id='codex', on_spawn=lambda *a: None)
    assert calls == [] and not P._catalogue_path(root).exists()


def test_legacy_last_good_models_do_not_gain_an_invented_model_observation(metadata):
    root, _, _ = metadata
    path = P._catalogue_path(root); path.parent.mkdir()
    path.write_text(json.dumps({'schema_version': 'laplace.provider-catalogue/1', 'observed_at': 999,
        'providers': [{'id': 'claude', 'available': False, 'model_catalogue_source': 'last-known-good',
                       'models': [{'id': 'old-model'}]}]}))
    P.capabilities(root, provider_id='codex')
    legacy = row(saved(root), 'claude')
    assert legacy['observed_at'] == 999 and legacy['model_observed_at'] is None
    assert legacy['model_catalogue_source'] == 'last-known-good'


def test_selected_claude_passes_spawn_attribution_through_auth_and_model_discovery(metadata, monkeypatch):
    root, _, _ = metadata
    callback = lambda *a: None
    phases = []
    def metadata_run(argv, **kwargs):
        assert kwargs['on_spawn'] is callback
        phases.append(kwargs['phase'])
        if kwargs['phase'] == 'claude-auth-discovery':
            return SimpleNamespace(stdout='{"loggedIn":true}')
        request = json.loads(kwargs['input'])
        assert request['request']['subtype'] == 'initialize'
        return SimpleNamespace(stdout=json.dumps({'type': 'control_response', 'response': {
            'request_id': 'laplace-models', 'subtype': 'success', 'response': {'models': [
                {'value': 'fixture-model', 'supportsEffort': False}]}}}))
    monkeypatch.setattr(P, '_metadata_run', metadata_run)
    monkeypatch.setattr(P, 'CodexConnection', lambda *a, **k: pytest.fail('unselected Codex'))
    result = P.capabilities(root, provider_id='claude', on_spawn=callback)
    assert phases == ['claude-auth-discovery', 'claude-model-discovery']
    assert row(result, 'claude')['models'][0]['supports_effort'] is False


@pytest.mark.parametrize('selection', [None, 'unrelated'])
def test_invalid_session_provider_never_becomes_a_full_catalogue_action(metadata, selection):
    root, _, calls = metadata
    with pytest.raises(P.ProviderError, match='Unknown writing provider'):
        turn_admission.effort_as_sent(root, {'provider': selection})
    assert calls == [] and not P._catalogue_path(root).exists()


def test_partial_memory_and_disk_reconcile_each_provider_before_read_and_late_write(metadata, monkeypatch):
    root, clock, _ = metadata
    clock[0] = 100
    baseline = {'schema_version': 'laplace.provider-catalogue/1', 'observed_at': 10, 'updated_at': 10,
        'observation_scope': {'kind': 'catalogue'}, 'providers': [
        {'id': name, 'available': True, 'observed_at': 10, 'model_observed_at': 10,
         'models': [{'id': 'old-' + name}]} for name in ('codex', 'claude')]}
    path = P._catalogue_path(root); path.parent.mkdir(); path.write_text(json.dumps(baseline))
    original = P.os.replace
    monkeypatch.setattr(P.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('persistence unavailable')))
    P.capabilities(root, refresh=True, provider_id='codex')
    monkeypatch.setattr(P.os, 'replace', original)
    concurrent = copy.deepcopy(baseline)
    concurrent.update(updated_at=90, observation_scope={'kind': 'provider', 'provider_id': 'claude'})
    row(concurrent, 'claude').update(observed_at=90, model_observed_at=90, models=[{'id': 'other-provider-new'}])
    path.write_text(json.dumps(concurrent))
    passive = C.provider_catalogue(root)
    assert row(passive, 'codex')['observed_at'] == 100
    assert row(passive, 'claude')['observed_at'] == row(passive, 'claude')['model_observed_at'] == 90
    assert row(passive, 'claude')['models'][0]['id'] == 'other-provider-new'
    assert passive['observed_at'] == 10 and passive['updated_at'] == 100
    cached_claude = P.capabilities(root, provider_id='claude')
    assert cached_claude['cached'] and row(cached_claude, 'claude')['models'][0]['id'] == 'other-provider-new'
    clock[0] = 101
    P.capabilities(root, refresh=True, provider_id='codex')
    persisted = saved(root)
    assert row(persisted, 'claude') == row(concurrent, 'claude')
    assert row(persisted, 'codex')['observed_at'] == 101 and persisted['observed_at'] == 10
    (root / 'provider-reconciliation-proof.json').write_text(json.dumps({
        'concurrent_disk': concurrent, 'passive_join': passive, 'persisted_join': persisted}, indent=2))


def test_reconciliation_keeps_latest_attempt_and_newest_proven_retained_models(metadata, monkeypatch):
    root, _, _ = metadata
    disk = {'schema_version': 'laplace.provider-catalogue/1', 'observed_at': 10, 'updated_at': 90,
        'providers': [{'id': 'claude', 'available': True, 'observed_at': 90, 'model_observed_at': 90,
                       'models': [{'id': 'new-proven-model'}]}]}
    memory = copy.deepcopy(disk); memory['updated_at'] = 110
    row(memory, 'claude').update(available=False, observed_at=110, model_observed_at=10,
        model_catalogue_source='last-known-good', model_discovery_error='latest attempt failed', models=[{'id': 'old-model'}])
    path = P._catalogue_path(root); path.parent.mkdir(); path.write_text(json.dumps(disk))
    monkeypatch.setattr(P, '_CAP_CACHE', (0, memory)); monkeypatch.setattr(P, '_CAP_CACHE_ROOT', root)
    result = row(C.provider_catalogue(root), 'claude')
    assert result['observed_at'] == 110 and result['available'] is False
    assert result['model_discovery_error'] == 'latest attempt failed'
    assert result['model_observed_at'] == 90 and result['models'][0]['id'] == 'new-proven-model'
    assert result['model_catalogue_source'] == 'last-known-good'


def test_live_session_validation_discovers_only_its_selected_provider(metadata):
    from laplace.work import project_work
    root, _, calls = metadata
    result = project_work.validate_session_settings({'provider': 'codex', 'model': 'fixture-model', 'effort': 'low'}, root)
    assert result['provider'] == 'codex' and result['model'] == 'fixture-model' and result['effort'] == 'low'
    assert [call[0] for call in calls] == ['codex', 'closed']


@pytest.mark.parametrize('selection', [None, 'unrelated'])
def test_invalid_live_session_validation_refuses_before_any_probe(metadata, selection):
    from laplace.work import project_work
    root, _, calls = metadata
    with pytest.raises(P.ProviderError, match='Unknown writing provider'):
        project_work.validate_session_settings({'provider': selection, 'model': 'fixture-model', 'effort': 'low'}, root)
    assert calls == [] and not P._catalogue_path(root).exists()
