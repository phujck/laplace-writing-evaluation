import hashlib
import json
from pathlib import Path
import pytest
from laplace.projects import library as wp
from laplace.manuscript import writing_style
from laplace.native import tools as writing_tools
from laplace.writing import provider as writing_provider
from laplace.writing import reads


def profiles(root):
    home = root / 'profiles/voice'; home.mkdir(parents=True)
    default = root / writing_style.DEFAULT_PROFILE
    default.write_text('# Default voice\nVersion: v1\n\n## Current runtime prompt\nKeep the reasoning connected.\n')
    other = home / 'other-v1.md'; other.write_text('# Other voice\nVersion: v1\n\n## Current runtime prompt\nUse concrete examples.\n')
    (root / 'runtime_profiles.toml').write_text('schema="laplace-runtime-profiles/1"\n[lifecycle]\npython="/configured/python"\nexpected_python="3.14.7"\n[development]\ndefault_profile="gpu"\n')
    return default, other


def catalogue(monkeypatch):
    from laplace.web import authoring as authoring_surface  # bind the real import before installing passive-read spies
    from laplace.writing import provider_catalogue as passive   # the neutral owner the passive reads consult
    monkeypatch.setattr(passive, 'provider_catalogue', lambda root: {'providers': [
        {'id': 'codex', 'name': 'Codex', 'available': False, 'auth_state': 'UNVERIFIED', 'models': []}], 'cached': True})
    monkeypatch.setattr(writing_provider, 'capabilities', lambda *a, **k: (_ for _ in ()).throw(AssertionError('provider discovery is forbidden on passive read')))


def test_global_configuration_and_voice_read_without_project_or_discovery(tmp_path, monkeypatch):
    profiles(tmp_path); catalogue(monkeypatch)
    from laplace.pipeline import registry
    monkeypatch.setattr(registry, 'resolve', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no dummy project resolution')))
    value = wp.app_settings(tmp_path)
    assert value['scope'] == 'application'
    assert value['providers']['cached'] is True
    assert value['model_policy']['row_source'].endswith('TIERS / WORKER_TIER')
    assert value['runtime']['declared']['development']['default_profile'] == 'gpu'
    assert 'runtime_content' not in value['voice']
    assert not (tmp_path / 'registry_projects.json').exists()
    observed = writing_tools.execute(tmp_path, '', 'discuss', 'app_settings', {'scope': 'application'}, turn_id='fixture-global-read')
    assert observed['scope'] == 'application' and observed['read_receipt']['operation'] == 'app_settings'
    assert 'app_settings' not in reads.WRITES and 'app_voice_change' not in reads.WRITES
    native = writing_tools.request(tmp_path, '', 'discuss', {'verb': 'read', 'concept': 'contract@project',
        'target': '', 'expected': [], 'payload': {'scope': 'application'}, 'by': 'author'})
    assert native['ok'] is True, native
    assert native['owner_response']['scope'] == 'application'


def test_global_voice_update_keeps_guards_and_project_tool_selected_profile_authority(tmp_path, monkeypatch):
    default, other = profiles(tmp_path); catalogue(monkeypatch)
    assert wp.create({'name': 'consumer', 'title': 'Consumer', 'kind': 'general'}, tmp_path)[0] == 201
    before_registry = (tmp_path / 'registry_projects.json').read_bytes()
    read = wp.app_settings(tmp_path, view='voice', profile=other.relative_to(tmp_path).as_posix())
    assert read['project'] is None and read['selected_profile'] is None and read['scope'] == 'global'
    payload = {'profile': read['profile'], 'content': '# Updated shared voice\nVersion: v2\n\n## Current runtime prompt\nExplain each consequence.\n',
        'expected_profile_revision': read['profile_revision'], 'basis': 'author_preference',
        'reason': 'Explicit operator preference.', 'provenance_kind': 'direct-author-instruction'}
    with pytest.raises(ValueError, match='currently selected profile'):
        writing_style.update_profile('consumer', {**payload, 'by': 'human'}, tmp_path)
    status, _, raw = wp.handle('/projects/app-settings', {}, 'POST', json.dumps({'action': 'voice-profile', **payload}).encode(), tmp_path)
    result = json.loads(raw)
    assert status == 200, result
    assert other.read_text() == payload['content']
    assert result['profile'] == read['profile'] and result['profile_revision'] != read['profile_revision']
    assert (tmp_path / 'registry_projects.json').read_bytes() == before_registry
    assert default.read_text().startswith('# Default voice')
    assert wp.handle('/projects/app-settings', {}, 'POST', json.dumps({'action': 'voice-profile', **payload}).encode(), tmp_path)[0] == 409
    assert wp.handle('/projects/app-settings', {}, 'POST', b'{"action":"global-model"}', tmp_path)[0] == 422


def test_workspace_dependency_catalogue_reads_registry_only_then_dereferences_exact_consumer(tmp_path, monkeypatch):
    source = tmp_path / 'shared.txt'; source.write_text('Shared owner bytes')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    rows = []
    for index in range(500):
        name = f'consumer-{index}'
        rows.append({'name': name, 'kind': 'project', 'project_dir': f'writing_projects/{name}',
            'manifest': {'display_name': f'Consumer {index}', 'material_references': [{
                'id': f'MAT-{index}', 'relation': 'uses-material',
                'target': {'owner': 'repository', 'repository': 'laplace', 'path': 'shared.txt'},
                'consumed_revision': digest, 'version_policy': 'pinned'}]}})
    (tmp_path / 'registry_projects.json').write_text(json.dumps({'projects': rows}))
    from laplace.work import project_work
    from laplace.research import literature_support
    monkeypatch.setattr(project_work, 'state', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no per-project summaries')))
    monkeypatch.setattr(literature_support, 'for_node', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no literature checks')))
    first = wp.material_references('', tmp_path, view='workspace', limit=20)
    assert first['total'] == 500 and first['next_offset'] == 20
    assert len(first['references']) == 20 and all(r['currentness'] == 'NOT_INSPECTED' for r in first['references'])
    assert 'owner_result' not in first['references'][0]
    page = writing_tools.execute(tmp_path, '', 'discuss', 'material_references', {'view': 'workspace', 'offset': 20, 'limit': 20})
    assert page['references'][0]['qualified_id'] == 'consumer-20::MAT-20'
    observed = writing_tools.execute(tmp_path, '', 'discuss', 'material_references', {'view': 'workspace-source', 'consumer': 'consumer-20', 'id': 'MAT-20', 'limit': 6})
    assert observed['project'] == 'consumer-20' and observed['currentness'] == 'CURRENT'
    assert observed['owner_result']['content'] == 'Shared'
    assert observed['read_handle']['payload']['view'] == 'workspace-source'
    source.write_text('Changed owner bytes')
    changed = wp.material_references('', tmp_path, view='workspace-source', consumer='consumer-20', id='MAT-20')
    assert changed['currentness'] == 'CHANGED_INPUT' and changed['consumed_revision'] == digest
    filtered = wp.material_references('', tmp_path, view='workspace', consumer='consumer-20', query='shared')
    assert filtered['total'] == 1
    assert any(r['kind'] == 'task-prerequisites' and 'project-local' in r['listing'] for r in filtered['coverage'])


def test_http_global_settings_and_workspace_dependencies_before_project_selection(tmp_path, monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.request import Request, urlopen
    from laplace.web import scanner
    _, other = profiles(tmp_path); catalogue(monkeypatch)
    monkeypatch.setattr(scanner, '_repo_root', lambda: tmp_path)
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), scanner.make_handler())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'
    def request(path, payload=None):
        req = Request(base + path, data=json.dumps(payload).encode() if payload else None,
            headers={'X-Laplace-Writing': '1', 'Content-Type': 'application/json'})
        with urlopen(req, timeout=5) as response:return response.status, json.loads(response.read())
    try:
        status, summary = request('/projects/app-settings')
        assert status == 200 and summary['scope'] == 'application'
        assert not (tmp_path / 'registry_projects.json').exists()
        _, deps = request('/projects/material-references?view=workspace')
        assert deps['scope'] == 'workspace' and deps['total'] == 0
        path = other.relative_to(tmp_path).as_posix()
        _, read = request('/projects/app-settings?view=voice&profile=' + path)
        status, saved = request('/projects/app-settings', {'action': 'voice-profile', 'profile': path,
            'content': '# Other voice\nVersion: v2\n\n## Current runtime prompt\nKeep examples precise.\n',
            'expected_profile_revision': read['profile_revision'], 'basis': 'author_preference',
            'reason': 'Explicit global author preference.', 'provenance_kind': 'direct-author-instruction'})
        assert status == 200 and saved['project'] is None
        assert not (tmp_path / 'registry_projects.json').exists()
        with pytest.raises(ValueError, match='selected registered project'):
            writing_style.update_profile(None, {'profile': path}, tmp_path)
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=2)


def test_workspace_dependency_continuation_pins_registry_for_http_and_native(tmp_path):
    rows = [{'name': f'consumer-{i}', 'kind': 'project', 'manifest': {
        'material_references': [{'id': f'MAT-{i}', 'relation': 'uses-material',
            'target': {'owner': 'repository', 'repository': 'laplace', 'path': 'shared.txt'},
            'consumed_revision': 'sha256:source'}]}} for i in range(25)]
    path = tmp_path / 'registry_projects.json'
    path.write_text(json.dumps({'projects': rows}))
    first = wp.material_references('', tmp_path, view='workspace', limit=20)
    continuation = first['next_read']['payload']
    second = writing_tools.execute(tmp_path, '', 'discuss', 'material_references', continuation)
    assert len({r['qualified_id'] for r in first['references'] + second['references']}) == 25
    path.write_text(json.dumps({'projects': [dict(rows[0], name='new-consumer'), *rows]}))
    with pytest.raises(ValueError, match='revision conflict'):
        writing_tools.execute(tmp_path, '', 'discuss', 'material_references', continuation)
    status, _, body = wp.handle('/projects/material-references',
        {k: [str(v)] for k, v in continuation.items()}, 'GET', b'', tmp_path)
    assert status == 409 and 'revision conflict' in json.loads(body)['error']
    fresh = wp.material_references('', tmp_path, view='workspace', limit=20)
    assert fresh['registry_revision'] != first['registry_revision'] and fresh['total'] == 26
    rest = writing_tools.execute(tmp_path, '', 'discuss', 'material_references', fresh['next_read']['payload'])
    ids = [r['qualified_id'] for r in fresh['references'] + rest['references']]
    assert len(ids) == len(set(ids)) == 26
