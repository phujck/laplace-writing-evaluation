"""Public synthetic definition-owner boundary cases; no provider is started."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import runtime_guard

from laplace.pipeline import workflow_definitions as D
from laplace.pipeline import workflow as W
from laplace.work import owner_discovery as O


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    runtime_guard.arm(monkeypatch)
    monkeypatch.delenv('LAPLACE_CUSTODY_LIVE', raising=False)
    (tmp_path / 'node.py').write_text('VALUE = 1\n')
    cache = tmp_path / '.laplace-cache'
    cache.mkdir()
    (cache / 'writing-provider-catalogue.json').write_text(json.dumps({
        'schema_version': 'laplace.provider-catalogue/1', 'observed_at': 99999999999,
        'providers': [{'id': 'codex', 'available': True, 'models': []},
                      {'id': 'claude', 'available': True, 'models': []}]}))
    return tmp_path


def definition():
    roles = [('review', 'group', None), ('author', 'builder', 'review'),
             ('critic', 'adversary', 'review'), ('synthesis', 'synthesis', 'review')]
    return {'schema_version': D.SCHEMA, 'title': 'Public fixture', 'description': '',
            'settings': {}, 'layout': {},
            'steps': [{'id': ident, 'title': ident, 'parent_id': parent,
                       'assignment': {'role': role, 'instructions': 'Inspect public fixture' if role != 'group' else '',
                                      'settings': {}}} for ident, role, parent in roles],
            'edges': [{'id': 'a-c', 'from': 'author', 'to': 'critic', 'kind': 'control'},
                      {'id': 'a-s', 'from': 'author', 'to': 'synthesis', 'kind': 'control'},
                      {'id': 'c-s', 'from': 'critic', 'to': 'synthesis', 'kind': 'control'}]}


def save(root, body=None, **kw):
    return D.save(root, O.owned_workspace('sdk'), {'request_id': 'create', 'expected_revision': None,
                  'definition': body or definition(), **kw})


def test_real_save_replay_stale_detachment_and_execution_selector_separation(workspace):
    root = workspace
    body = definition()
    first = save(root, body)
    identity = first['definition_id']
    raw = (root / W.LEDGER).read_bytes()
    assert save(root, body)['replayed'] is True
    assert (root / W.LEDGER).read_bytes() == raw
    body['title'] = 'Changed'
    with pytest.raises(D.Refused, match='REQUEST'):
        save(root, body)
    second = save(root, body, request_id='edit', definition_id=identity, expected_revision=first['version'])
    assert second['version'] != first['version']
    with pytest.raises(D.Refused, match='STALE'):
        save(root, body, request_id='stale', definition_id=identity, expected_revision=first['version'])
    historical = D.read(root, O.owned_workspace('sdk'), {'definition_id': identity, 'version': first['version']})
    assert historical['currentness'] == 'HISTORICAL' and historical['definition']['title'] == 'Public fixture'
    historical['definition']['title'] = 'Mutated consumer copy'
    assert D.read(root, O.owned_workspace('sdk'), {'definition_id': identity})['definition']['title'] == 'Changed'
    rows = [json.loads(line) for line in (root / W.LEDGER).read_text().splitlines()]
    assert all(row['record'] != 'workflow' and 'workflow_id' not in row for row in rows)
    assert W.recent_workflows(root)['workflows'] == []


def test_scope_is_host_fact_and_reference_admission_is_exact(workspace):
    root = workspace
    first = save(root, scope={'kind': 'project', 'namespace': 'book'})
    assert D.read(root, O.project_scope('book', 'native'), {'definition_id': first['definition_id']})['definition_id'] == first['definition_id']
    with pytest.raises(D.Refused, match='NOT_IN_SCOPE'):
        D.read(root, O.project_scope('other', 'native'), {'definition_id': first['definition_id']})
    assert D.read(root, O.project_scope('other', 'native'), {})['definitions'] == []
    reference = first['reference']
    for bad in [{**reference, 'owner': 'made-up'}, {**reference, 'kind': 'work'},
                {**reference, 'version': {'unsupported': first['version']}}]:
        with pytest.raises(D.Refused):
            D.read(root, O.owned_workspace('sdk'), {'reference': bad})
    with pytest.raises(D.Refused):
        save(root, definition_id=first['definition_id'], request_id='escalate', expected_revision=first['version'],
             scope={'kind': 'owned-workspace'})


def test_supported_partial_prepare_pins_v4_while_v5_feedback_draft_saves(workspace):
    root = workspace
    body = definition()
    body['steps'].append({'id': 'unfinished', 'title': 'Later', 'parent_id': None,
                         'assignment': {'role': 'builder', 'instructions': '', 'settings': {}}})
    first = save(root, body)
    payload = {'request_id': 'prepare', 'reference': first['reference'],
               'selected_steps': ['author', 'critic', 'synthesis'], 'profile': W.SPEC_SCHEMA,
               'node': 'node.py', 'goal': 'Public fixture only', 'write_paths': ['node.py']}
    prepared = D.prepare(root, O.owned_workspace('sdk'), payload)
    assert prepared['status'] == 'NOT_STARTED'
    manifest = W._manifest(root / prepared['run_path'])
    assert manifest['definition_pin']['definition_revision'] == first['version']
    assert D.prepare(root, O.owned_workspace('sdk'), payload)['run_id'] == prepared['run_id']
    body['edges'].append({'id': 'feedback', 'from': 'critic', 'to': 'author', 'kind': 'feedback'})
    second = save(root, body, request_id='v5', definition_id=first['definition_id'], expected_revision=first['version'])
    assert W._manifest(root / prepared['run_path']) == manifest
    with pytest.raises(D.Refused, match='UNSUPPORTED'):
        D.prepare(root, O.owned_workspace('sdk'), {**payload, 'request_id': 'cycle', 'reference': second['reference']})
    assert D.read(root, O.owned_workspace('sdk'), {'definition_id': first['definition_id']})['definition']['edges'][-1]['kind'] == 'feedback'
    assert not [row for row in map(json.loads, (root / W.LEDGER).read_text().splitlines()) if row.get('phase') == 'start']


def test_containment_cycle_refuses_and_setting_basis_excludes_shadowed_display(workspace):
    root = workspace
    body = definition()
    body['steps'][0]['parent_id'] = 'author'
    with pytest.raises(D.Refused, match='CONTAINMENT'):
        save(root, body)
    body = definition()
    body['steps'][1]['assignment']['settings'] = {'model': 'explicit-model', 'provider': 'codex', 'effort': 'high'}
    first = save(root, body)
    body['settings']['model'] = 'changed-inherited-model'
    body['layout'] = {'review': {'x': 50, 'y': 80}}
    second = save(root, body, request_id='shadow', definition_id=first['definition_id'], expected_revision=first['version'])
    assert first['effective_settings']['author']['consumed_settings_digest'] == second['effective_settings']['author']['consumed_settings_digest']
    assert first['effective_settings']['critic']['consumed_settings_digest'] != second['effective_settings']['critic']['consumed_settings_digest']


def test_export_restore_preserves_identity_all_versions_and_body_custody_after_move(workspace, tmp_path):
    root = workspace
    first = save(root)
    body = definition()
    body['title'] = 'Second saved version'
    second = save(root, body, request_id='second', definition_id=first['definition_id'], expected_revision=first['version'])
    package = D.read(root, O.owned_workspace('sdk'), {'definition_id': first['definition_id'], 'facet': 'export'})
    destination = root / 'unrelated-custody-location'
    destination.mkdir()
    result = D.restore(destination, O.owned_workspace('sdk'), package)
    assert result['definition_id'] == first['definition_id'] and result['version'] == second['version']
    assert result['scope_id'] != second['scope_id']
    assert D.read(destination, O.owned_workspace('sdk'), {'reference': first['reference']})['definition']['title'] == first['definition']['title']
    assert D.restore(destination, O.owned_workspace('sdk'), package)['version'] == second['version']
    broken = copy.deepcopy(package)
    broken['versions'][0]['definition']['title'] = 'Tampered'
    with pytest.raises(D.Refused, match='INVALID_EXPORT'):
        D.restore(root / 'bad', O.owned_workspace('sdk'), broken)


def test_validate_export_is_pure_detached_and_preserves_transfer_facts(workspace, monkeypatch):
    first = save(workspace)
    body = definition(); body['title'] = 'Second immutable version'
    save(workspace, body, request_id='second', definition_id=first['definition_id'], expected_revision=first['version'])
    package = D.read(workspace, O.owned_workspace('sdk'), {'definition_id': first['definition_id'], 'facet': 'export'})
    with monkeypatch.context() as patch:
        forbidden = lambda *a, **k: pytest.fail('pure export validation consulted owner custody')
        patch.setattr(D, '_root', forbidden); patch.setattr(D, '_rows', forbidden)
        patch.setattr(D.writing_bodies, 'store', forbidden)
        checked = D.validate_export(package)
        assert checked == package and checked is not package
        checked['versions'][0]['definition']['title'] = 'Detached edit'
        assert package['versions'][0]['definition']['title'] != 'Detached edit'
        broken = copy.deepcopy(package); broken['versions'][0]['definition']['title'] = 'Broken body'
        with pytest.raises(D.Refused, match='INVALID_EXPORT_CHAIN'):
            D.validate_export(broken)
        duplicate = copy.deepcopy(package)
        duplicate['versions'][1]['row']['request_id'] = duplicate['versions'][0]['row']['request_id']
        duplicate['versions'][1]['row']['receipt']['request_id'] = duplicate['versions'][0]['row']['request_id']
        with pytest.raises(D.Refused, match='INVALID_EXPORT_REQUEST_DUPLICATE'):
            D.validate_export(duplicate)
    destination = workspace / 'pure-validator-transfer'; destination.mkdir()
    D.restore(destination, O.owned_workspace('sdk'), package)
    restored = D.read(destination, O.owned_workspace('sdk'), {'definition_id': first['definition_id'], 'facet': 'export'})
    for original, moved in zip(package['versions'], restored['versions']):
        assert moved['definition'] == original['definition']
        assert moved['row']['receipt'] == original['row']['receipt']
        assert moved['row']['request_id'] == original['row']['request_id']
        assert moved['row']['ts_claimed'] == original['row'].get('ts_claimed', original['row']['ts'])


def test_real_sdk_http_and_project_confined_native_reads(workspace):
    from laplace import sdk
    from laplace.web import project_work_surface
    from laplace.work import project_work_views
    root = workspace
    payload = {'request_id': 'http-create', 'expected_revision': None, 'definition': definition(),
               'scope': {'kind': 'project', 'namespace': 'book'}}
    code, _, raw = project_work_surface.handle('/work/workflow-definitions/save', {}, 'POST', json.dumps(payload).encode(), root)
    assert code == 200
    saved = json.loads(raw)
    assert saved['effect'] == 'saved' and saved['receipt']['definition_revision'] == saved['version']
    assert sdk.workflow_request({'definition_id': saved['definition_id']}, root=root)['definition'] == saved['definition']
    native = project_work_views.read('book', {'view': 'workflow-definitions', 'request': {'definition_id': saved['definition_id']}}, root, mode='native')
    assert native['definition_id'] == saved['definition_id'] and native['actions']['save']['permitted'] is False
    with pytest.raises(D.Refused, match='NOT_IN_SCOPE'):
        project_work_views.read('other', {'view': 'workflow-definitions', 'request': {'definition_id': saved['definition_id']}}, root, mode='native')
    stale = {**payload, 'request_id': 'stale-http', 'definition_id': saved['definition_id'], 'expected_revision': 'sha256:' + '0' * 64}
    code, _, raw = project_work_surface.handle('/work/workflow-definitions/save', {}, 'POST', json.dumps(stale).encode(), root)
    assert code == 409 and json.loads(raw)['code'] == 'STALE_EDIT'


def test_requested_work_target_guard_is_rechecked_inside_actual_work_writer_lock(workspace, monkeypatch):
    from filelock import FileLock
    from laplace.work import project_work
    root = workspace
    project_work.task('book', {'id': 'target', 'title': 'Synthetic target', 'goal': 'Public fixture'}, root)
    original_revision = project_work._task_revision(project_work._tasks('book', root)['target'])
    ref = O.work_reference('book', 'target', revision=original_revision)
    body = definition()
    body['steps'][1]['targets'] = [{'reference': ref, 'mode': 'current-action'}]
    original_lock = D._lock
    touched = []
    def at_publication(base):
        # The definition owner takes the existing Work lock BEFORE its definition lock.
        # A competing thread cannot acquire the actual Work lock at this boundary.
        import threading
        def competitor():
            try:
                with FileLock(str(project_work._ledger(base)) + '.lock', timeout=0):
                    touched.append('unsafe')
            except TimeoutError:
                touched.append('blocked')
        thread = threading.Thread(target=competitor)
        thread.start(); thread.join()
        return original_lock(base)
    monkeypatch.setattr(D, '_lock', at_publication)
    first = save(root, body)
    assert touched == ['blocked']
    project_work.task('book', {'id': 'target', 'title': 'Changed external instruction', 'goal': 'Public fixture',
                             'expected_work_revision': original_revision}, root)
    with pytest.raises(D.Refused, match='STALE_TARGET'):
        save(root, body, request_id='stale-target', definition_id=first['definition_id'], expected_revision=first['version'])


def test_unsupported_target_and_provider_are_local_drafts_without_fabricated_execution(workspace):
    body = definition()
    body['steps'][1]['targets'] = [{'reference': {'owner': 'unknown'}, 'mode': 'historical'}]
    body['steps'][1]['assignment']['settings'] = {'provider': 'claude', 'model': 'sonnet'}
    saved = save(workspace, body)
    assert saved['obligations'] and saved['actions']['save']['permitted']
    with pytest.raises(D.Refused, match='UNSUPPORTED_PROVIDER'):
        D.prepare(workspace, O.owned_workspace('sdk'), {'request_id': 'claude-profile', 'reference': saved['reference'],
                  'selected_steps': ['author', 'critic', 'synthesis'], 'profile': W.SPEC_SCHEMA,
                  'node': 'node.py', 'goal': 'Public fixture', 'write_paths': []})


def test_historical_save_retains_original_guard_until_explicit_comparison(workspace):
    first = save(workspace)
    body = definition(); body['description'] = 'New head instructions'
    second = save(workspace, body, request_id='new-head', definition_id=first['definition_id'], expected_revision=first['version'])
    old = D.read(workspace, O.owned_workspace('sdk'), {'reference': first['reference']})
    assert old['edit_revision'] == first['version'] and old['head_revision'] == second['version']
    with pytest.raises(D.Refused, match='STALE_EDIT'):
        D.save(workspace, O.owned_workspace('sdk'), {**old['actions']['save']['payload'],
               'request_id': 'old-edit', 'definition': old['definition']})
    assert len(D.read(workspace, O.owned_workspace('sdk'), {'reference': first['reference'], 'facet': 'export'})['versions']) == 1


def test_prepare_recovers_exact_manifest_before_declaration_without_duplicate_run(workspace, monkeypatch):
    first = save(workspace)
    payload = {'request_id': 'partial', 'reference': first['reference'], 'selected_steps': ['author', 'critic', 'synthesis'],
               'profile': W.SPEC_SCHEMA, 'node': 'node.py', 'goal': 'Public fixture', 'write_paths': []}
    original = W._bank
    def fail_declaration(root, row):
        if row['record'] == 'workflow':
            raise OSError('synthetic interruption before declaration')
        return original(root, row)
    monkeypatch.setattr(W, '_bank', fail_declaration)
    with pytest.raises(D.Refused, match='PREPARATION_UNCERTAIN') as refusal:
        D.prepare(workspace, O.owned_workspace('sdk'), payload)
    assert refusal.value.details['effect'] == 'unknown'
    assert len(list((workspace / 'evidence' / 'WORKFLOWS').glob('*/run.json'))) == 1
    monkeypatch.setattr(W, '_bank', original)
    result = D.prepare(workspace, O.owned_workspace('sdk'), payload)
    assert result['replayed'] and result['status'] == 'NOT_STARTED'
    assert len(list((workspace / 'evidence' / 'WORKFLOWS').glob('*/run.json'))) == 1
    monkeypatch.setattr(D, 'resolve_settings', lambda *a, **kw: pytest.fail('completed preparation re-resolved mutable defaults'))
    assert D.prepare(workspace, O.owned_workspace('sdk'), payload)['run_id'] == result['run_id']


def test_nested_inherited_settings_and_explicit_instruction_scope(workspace):
    body = definition()
    body['settings'] = {'model': 'root-default', 'provider': 'codex', 'effort': 'medium'}
    body['steps'][0]['assignment']['settings'] = {'model': 'review-default'}
    body['steps'][0]['assignment']['instructions'] = 'Shared purpose displayed, not silently concatenated'
    body['steps'][1]['assignment']['settings'] = {'model': 'explicit-author'}
    result = save(workspace, body)
    assert result['effective_settings']['critic']['model']['value'] == 'review-default'
    assert result['effective_settings']['critic']['model']['origin'] == 'assignment:review'
    assert result['effective_settings']['author']['model']['value'] == 'explicit-author'
    assert result['effective_settings']['author']['instruction']['value'] == 'Inspect public fixture'
    assert result['effective_settings']['author']['instruction']['composition'].startswith('local exact')
    assert result['effective_settings']['critic']['model']['admitted_override'].endswith('no execution/source/tool grant')


def test_native_real_tool_read_cannot_promote_role_or_scope(workspace):
    from laplace.native import tools
    saved = save(workspace, scope={'kind': 'project', 'namespace': 'book'})
    answer = tools.execute(workspace, 'book', 'discuss', 'project',
                           {'view': 'workflow-definitions', 'request': {'definition_id': saved['definition_id']}})
    assert answer['definition_id'] == saved['definition_id']
    with pytest.raises(D.Refused, match='NATIVE_WRITE_NOT_ADMITTED'):
        D.save(workspace, O.project_scope('book', 'native'), {'request_id': 'native-write', 'expected_revision': None,
                                                             'definition': definition()})


def test_lost_create_and_prepare_response_recovery_is_request_qualified_and_scoped(workspace):
    first = save(workspace, scope={'kind': 'project', 'namespace': 'book'})
    recovered = D.read(workspace, O.project_scope('book', 'native'), {'facet': 'request', 'request_id': 'create'})
    assert recovered['status'] == 'RECORDED' and recovered['effect'] == 'saved'
    assert recovered['receipt'] == first['receipt'] and recovered['read'] == first['read']
    absent = D.read(workspace, O.project_scope('other', 'native'), {'facet': 'request', 'request_id': 'create'})
    assert absent['status'] == 'NOT_RECORDED' and absent['effect'] == 'unknown'
    payload = {'request_id': 'prepare-recover', 'reference': first['reference'], 'selected_steps': ['author', 'critic', 'synthesis'],
               'profile': W.SPEC_SCHEMA, 'node': 'node.py', 'goal': 'Public fixture', 'write_paths': []}
    prepared = D.prepare(workspace, O.owned_workspace('sdk'), payload)
    recovered = D.read(workspace, O.owned_workspace('sdk'), {'facet': 'request', 'request_id': 'prepare-recover'})
    assert recovered['status'] == 'RECORDED' and recovered['run']['status'] == 'NOT_STARTED'
    assert recovered['receipt'] == prepared['receipt']


def test_effect_receipt_survives_unavailable_postimage_and_restore_resumes_prefix(workspace, monkeypatch):
    original = D._view
    monkeypatch.setattr(D, '_view', lambda *args: (_ for _ in ()).throw(D.Refused('UNAVAILABLE_VERSION')))
    saved = save(workspace)
    assert saved['effect'] == 'saved' and saved['receipt']['definition_revision'] == saved['version']
    assert saved['observation']['status'] == 'UNAVAILABLE'
    monkeypatch.setattr(D, '_view', original)
    body = definition(); body['title'] = 'Later version'
    newer = save(workspace, body, request_id='v2', definition_id=saved['definition_id'], expected_revision=saved['version'])
    package = D.read(workspace, O.owned_workspace('sdk'), {'definition_id': saved['definition_id'], 'facet': 'export'})
    destination = workspace / 'restore-prefix'
    prefix = {**package, 'versions': package['versions'][:1]}
    D.restore(destination, O.owned_workspace('sdk'), prefix)
    restored = D.restore(destination, O.owned_workspace('sdk'), package)
    assert restored['version'] == newer['version'] and len(restored['history']) == 2


def test_native_namespace_selector_cannot_replace_bound_project_scope(workspace):
    from laplace.native import tools
    saved = save(workspace, scope={'kind': 'project', 'namespace': 'other'})
    with pytest.raises(ValueError):
        tools.execute(workspace, 'book', 'discuss', 'project', {'view': 'workflow-definitions', 'namespace': 'other',
                      'request': {'definition_id': saved['definition_id']}})


def test_opaque_saved_step_ids_map_stably_to_legacy_packets_without_identity_change(workspace):
    body = definition()
    rename = {'author': '1-author', 'critic': 'CRITIC', 'synthesis': '9' * 70}
    for step in body['steps']:
        step['id'] = rename.get(step['id'], step['id'])
    for edge in body['edges']:
        edge['from'] = rename.get(edge['from'], edge['from']); edge['to'] = rename.get(edge['to'], edge['to'])
    # Deliberately occupy the first deterministic packet alias; mapping must resolve it.
    collision = 'step-' + W.digest(b'1-author').removeprefix('sha256:')[:40]
    body['steps'].append({'id': collision, 'title': 'Independent reserved name', 'parent_id': None,
                         'assignment': {'role': 'group', 'instructions': '', 'settings': {}}})
    first = save(workspace, body)
    selected = list(rename.values())
    payload = {'request_id': 'opaque-ids', 'reference': first['reference'], 'selected_steps': selected,
               'profile': W.SPEC_SCHEMA, 'node': 'node.py', 'goal': 'Public fixture', 'write_paths': []}
    prepared = D.prepare(workspace, O.owned_workspace('sdk'), payload)
    mapping = prepared['receipt']['step_stage_ids']
    assert set(mapping) == set(selected) and len(set(mapping.values())) == len(selected)
    assert mapping['1-author'] != collision and all(W._ID.fullmatch(value) for value in mapping.values())
    manifest = W._manifest(workspace / prepared['run_path'])
    assert manifest['definition_pin']['step_stage_ids'] == mapping
    assert manifest['spec']['stages'][1]['depends_on'] == [mapping['1-author']]
    assert set(manifest['spec']['stages'][-1]['depends_on']) == {mapping['1-author'], mapping['CRITIC']}
    assert D.read(workspace, O.owned_workspace('sdk'), {'reference': first['reference']})['definition'] == body
    assert D.prepare(workspace, O.owned_workspace('sdk'), payload)['receipt']['step_stage_ids'] == mapping


def test_committed_effect_keeps_truth_when_postimage_or_manifest_projection_fails(workspace, monkeypatch):
    original_view = D._view
    monkeypatch.setattr(D, '_view', lambda *args: (_ for _ in ()).throw(TypeError('synthetic projection failure')))
    saved = save(workspace)
    assert saved['effect'] == 'saved' and saved['observation']['status'] == 'UNAVAILABLE'
    monkeypatch.setattr(D, '_view', original_view)
    payload = {'request_id': 'manifest-read-failure', 'reference': D.reference(saved['definition_id'], saved['version']),
               'selected_steps': ['author', 'critic', 'synthesis'], 'profile': W.SPEC_SCHEMA,
               'node': 'node.py', 'goal': 'Public fixture', 'write_paths': []}
    original_manifest = W._manifest
    monkeypatch.setattr(W, '_manifest', lambda *args: (_ for _ in ()).throw(W.WorkflowRefused('synthetic observation failure')))
    with pytest.raises(D.Refused, match='PREPARATION_UNCERTAIN') as refusal:
        D.prepare(workspace, O.owned_workspace('sdk'), payload)
    assert refusal.value.details['effect'] == 'unknown'
    monkeypatch.setattr(W, '_manifest', original_manifest)
    recovered = D.read(workspace, O.owned_workspace('sdk'), {'facet': 'request', 'request_id': payload['request_id']})
    assert recovered['status'] == 'RECORDED' and recovered['effect'] == 'prepared'
    assert len(list((workspace / 'evidence' / 'WORKFLOWS').glob('*/run.json'))) == 1


def test_restore_validates_exact_receipt_record_and_destination_request_identity(workspace):
    first = save(workspace)
    package = D.read(workspace, O.owned_workspace('sdk'), {'definition_id': first['definition_id'], 'facet': 'export'})
    for field in ('definition_id', 'definition_revision', 'body_handle', 'request_id'):
        bad = copy.deepcopy(package)
        bad['versions'][0]['row']['receipt'][field] = 'tampered'
        with pytest.raises(D.Refused, match='INVALID_EXPORT_RECEIPT'):
            D.restore(workspace / ('bad-' + field), O.owned_workspace('sdk'), bad)
    bad = copy.deepcopy(package); bad['versions'][0]['row']['workflow_id'] = 'WORKFLOW-fake'
    with pytest.raises(D.Refused, match='INVALID_EXPORT_RECORD'):
        D.restore(workspace / 'bad-selector', O.owned_workspace('sdk'), bad)
    destination = workspace / 'request-collision'
    save(destination)  # Same request ID names a different actual definition here.
    with pytest.raises(D.Refused, match='RESTORE_REQUEST_CONFLICT'):
        D.restore(destination, O.owned_workspace('sdk'), package)
    assert len(D.read(destination, O.owned_workspace('sdk'), {})['definitions']) == 1


def test_request_identity_cannot_name_both_save_and_prepare_effects(workspace):
    first = save(workspace)
    payload = {'request_id': 'create', 'reference': first['reference'], 'selected_steps': ['author', 'critic', 'synthesis'],
               'profile': W.SPEC_SCHEMA, 'node': 'node.py', 'goal': 'Public fixture', 'write_paths': []}
    with pytest.raises(D.Refused, match='REQUEST_CONFLICT'):
        D.prepare(workspace, O.owned_workspace('sdk'), payload)
    D.prepare(workspace, O.owned_workspace('sdk'), {**payload, 'request_id': 'prepared'})
    with pytest.raises(D.Refused, match='REQUEST_CONFLICT'):
        save(workspace, request_id='prepared')


def test_orphan_preparation_reserves_request_identity_against_save_and_restore(workspace, monkeypatch):
    first = save(workspace)
    payload = {'request_id': 'orphan', 'reference': first['reference'], 'selected_steps': ['author', 'critic', 'synthesis'],
               'profile': W.SPEC_SCHEMA, 'node': 'node.py', 'goal': 'Public fixture', 'write_paths': []}
    original_bank = W._bank
    def fail_declaration(root, row):
        if row['record'] == 'workflow':raise OSError('synthetic lost declaration')
        return original_bank(root, row)
    monkeypatch.setattr(W, '_bank', fail_declaration)
    with pytest.raises(D.Refused, match='PREPARATION_UNCERTAIN'):
        D.prepare(workspace, O.owned_workspace('sdk'), payload)
    monkeypatch.setattr(W, '_bank', original_bank)
    with pytest.raises(D.Refused, match='REQUEST_CONFLICT'):
        save(workspace, request_id='orphan')
    source = workspace / 'import-source'
    imported = save(source, request_id='orphan')
    package = D.read(source, O.owned_workspace('sdk'), {'definition_id': imported['definition_id'], 'facet': 'export'})
    with pytest.raises(D.Refused, match='RESTORE_REQUEST_CONFLICT'):
        D.restore(workspace, O.owned_workspace('sdk'), package)
    recovered = D.read(workspace, O.owned_workspace('sdk'), {'facet': 'request', 'request_id': 'orphan'})
    assert recovered['status'] == 'PREPARATION_UNCERTAIN'
    assert D.prepare(workspace, O.owned_workspace('sdk'), payload)['status'] == 'NOT_STARTED'


def test_unrelated_malformed_candidate_is_local_for_save_restore_and_unknown_recovery(workspace):
    corrupt = workspace / 'evidence' / 'WORKFLOWS' / 'WORKFLOW-20000101T000000Z-000000000000'
    corrupt.mkdir(parents=True); (corrupt / 'run.json').write_text('{malformed unrelated legacy run')
    first = save(workspace)
    assert first['request_coverage']['status'] == 'PARTIAL'
    assert D.read(workspace, O.owned_workspace('sdk'), {'reference': first['reference']})['definition']['title'] == first['definition']['title']
    unknown = D.read(workspace, O.owned_workspace('sdk'), {'facet': 'request', 'request_id': 'not-recorded'})
    assert unknown['effect'] == 'unknown' and unknown['request_coverage']['status'] == 'PARTIAL'
    confined = D.read(workspace, O.project_scope('book', 'native'), {'facet': 'request', 'request_id': 'not-recorded'})
    assert confined['effect'] == 'unknown' and confined['request_coverage']['status'] == 'LIMITED'
    assert 'WORKFLOW-' not in json.dumps(confined) and 'inspected' not in confined['request_coverage']
    source = workspace / 'source'; imported = save(source, request_id='imported')
    package = D.read(source, O.owned_workspace('sdk'), {'definition_id': imported['definition_id'], 'facet': 'export'})
    restored = D.restore(workspace, O.owned_workspace('sdk'), package)
    assert restored['definition_id'] == imported['definition_id'] and restored['request_coverage']['status'] == 'PARTIAL'
    payload = {'request_id': 'declared-unreadable', 'reference': first['reference'], 'selected_steps': ['author', 'critic', 'synthesis'],
               'profile': W.SPEC_SCHEMA, 'node': 'node.py', 'goal': 'Public fixture', 'write_paths': []}
    prepared = D.prepare(workspace, O.owned_workspace('sdk'), payload)
    (workspace / prepared['run_path'] / 'run.json').write_text('{known matching declaration, damaged manifest')
    before = len(list((workspace / 'evidence' / 'WORKFLOWS').glob('*/run.json')))
    recorded = D.read(workspace, O.owned_workspace('sdk'), {'facet': 'request', 'request_id': payload['request_id']})
    assert recorded['status'] == 'UNAVAILABLE' and recorded['effect'] == 'unknown'
    with pytest.raises(D.Refused, match='PREPARATION_UNCERTAIN'):
        D.prepare(workspace, O.owned_workspace('sdk'), payload)
    assert len(list((workspace / 'evidence' / 'WORKFLOWS').glob('*/run.json'))) == before


def test_candidate_coverage_is_bounded_without_foreign_namespace_counts(workspace, monkeypatch):
    monkeypatch.setattr(D, 'CANDIDATE_LIMIT', 1)
    for suffix in ('000000000001', '000000000002'):
        directory = workspace / 'evidence' / 'WORKFLOWS' / ('WORKFLOW-20000101T000000Z-' + suffix)
        directory.mkdir(parents=True); (directory / 'run.json').write_text('{}')
    saved = save(workspace)
    assert saved['request_coverage']['status'] == 'PARTIAL' and saved['request_coverage']['inspected'] == 1
    assert saved['request_coverage']['remaining'] == 'UNKNOWN'


def test_no_fcntl_import_reach_preserves_old_doors_and_qualifies_selected_execution(workspace, tmp_path):
    """Simulated unavailable import in a fresh interpreter; not actual Windows parity."""
    import os
    import subprocess
    import sys
    source = Path(__file__).resolve().parents[1]
    helper = tmp_path / 'no-fcntl.py'
    helper.write_text('''import importlib.machinery,json,os,sys
from pathlib import Path
source=Path(os.environ['WORKFLOW_SOURCE']).resolve()
assert not any(name=='laplace' or name.startswith('laplace.') for name in sys.modules)
sys.path.insert(0,str(source/'tests'))
import runtime_guard
runtime_guard.install();runtime_guard.ARMED=True
class Selected:
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('laplace','atlas') or fullname.startswith(('laplace.','atlas.')):
   spec=importlib.machinery.PathFinder.find_spec(fullname,path)
   if spec and spec.origin and spec.origin not in ('built-in','frozen'):assert Path(spec.origin).resolve().is_relative_to(source/'src')
   return spec
sys.meta_path.insert(0,Selected())
sys.modules['fcntl']=None
from laplace.core import checkout
assert checkout.source_tree()==source and checkout.repo_root()==source
from laplace import sdk
from laplace.web import writing_server,project_work_surface
from laplace.native import tools
root=Path(os.environ['WORKFLOW_PORTABLE_ROOT'])
assert sdk.describe(root=root)['schema_version']=='laplace.owner-discovery/1'
code,_,raw=project_work_surface.handle('/work/state',{'view':['namespaces']},'GET',repo_root=root)
assert code==200
assert tools.execute(root,'book','discuss','project',{'view':'workflow-definitions'})['definitions']==[]
body=json.loads(os.environ['WORKFLOW_BODY'])
saved=sdk.workflow_save({'request_id':'portable-save','expected_revision':None,'definition':body},root=root)
assert saved['effect']=='saved' and sdk.workflow_request({'reference':saved['reference']},root=root)['version']==saved['version']
prepared=sdk.workflow_prepare({'request_id':'portable-prepare','reference':saved['reference'],'selected_steps':['author','critic','synthesis'],'profile':'laplace.workflow/1','node':'node.py','goal':'Public fixture','write_paths':[]},root=root)
assert prepared['status']=='NOT_STARTED'
from laplace.pipeline import workflow
before=(root/workflow.LEDGER).read_bytes()
try:workflow.run_workflow(root/prepared['run_path'],executor=lambda *_: (_ for _ in ()).throw(AssertionError('provider must not start')))
except workflow.WorkflowRefused as error:assert str(error).startswith('EXECUTION-PLATFORM-UNSUPPORTED')
else:raise AssertionError('unsupported execution was not qualified')
assert (root/workflow.LEDGER).read_bytes()==before and not (root/prepared['run_path']/'runner.lock').exists()
assert runtime_guard.DENIALS==[]
print(json.dumps({'status':'PASS','simulation':'fcntl import unavailable; not actual Windows parity','old_doors':['SDKdescribe','HTTPnamespaces','nativeprojectread'],'new':['definitionSave/read','PrepareNOT_STARTED'],'selected_execution':'typed refusal before lock/ledger/provider effect','guard_denials':runtime_guard.DENIALS}))
''')
    env = {**os.environ, 'WORKFLOW_SOURCE': str(source), 'WORKFLOW_PORTABLE_ROOT': str(workspace),
           'WORKFLOW_BODY': json.dumps(definition())}
    result = subprocess.run([sys.executable, '-I', '-B', str(source / 'scripts' / 'laplace_python.py'), str(helper)],
                            env=env, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['status'] == 'PASS'


def test_historical_export_bounds_selected_prefix_after_more_than_32_total_versions(workspace):
    first = save(workspace)
    current = first
    for index in range(1, 33):
        body = definition(); body['title'] = 'Saved version ' + str(index)
        current = save(workspace, body, request_id='history-' + str(index), definition_id=first['definition_id'],
                       expected_revision=current['version'])
    package = D.read(workspace, O.owned_workspace('sdk'), {'reference': first['reference'], 'facet': 'export'})
    assert len(package['versions']) == 1
    assert package['versions'][0]['row']['definition_revision'] == first['version']
    assert package['versions'][0]['definition'] == first['definition']
    with pytest.raises(D.Refused, match='EXPORT_BOUND'):
        D.read(workspace, O.owned_workspace('sdk'), {'reference': current['reference'], 'facet': 'export'})
