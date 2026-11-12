from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest
from laplace.web import project_work_surface, writing_server
from laplace.writing import operating as writing_operating
from laplace.projects import writing_storage
from laplace.writing import operations
from laplace.writing import reads


@pytest.fixture
def stores(tmp_path, monkeypatch):
    root = tmp_path / 'checkout'
    root.mkdir()
    (root / 'profiles').mkdir()
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [
        {'name': 'one', 'project_dir': 'projects/one', 'manuscript_dir': 'projects/one/manuscript'},
        {'name': 'two', 'project_dir': 'projects/two'}]}))
    (root / 'projects/one/manuscript/editor_saves').mkdir(parents=True)
    (root / 'projects/one/manuscript/source.tex').write_bytes(b'unchanged source')
    (root / 'projects/one/manuscript/editor_saves/version').write_bytes(b'old version')
    (root / 'contract').mkdir()
    (root / 'contract/talk.jsonl').write_text(json.dumps(
        {'record': 'writing-session', 'id': 'saved-two', 'project': 'two'})+'\n')
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES', str(tmp_path / 'cwd'))
    monkeypatch.setenv('LAPLACE_REPO_ROOT', str(root))
    monkeypatch.setenv('LAPLACE_WRITING_APP', '1')
    monkeypatch.setenv('LAPLACE_NO_PREWARM', '1')
    return root


@pytest.mark.parametrize('platform,environment,suffix', [
    ('linux', {}, '.local/share/laplace'),
    ('linux', {'XDG_DATA_HOME': '/explicit/data'}, '/explicit/data/laplace'),
    ('darwin', {}, 'Library/Application Support/Laplace'),
    ('win32', {}, 'AppData/Local/Laplace'),
    ('win32', {'LOCALAPPDATA': '/explicit/local'}, '/explicit/local/Laplace')])
def test_platform_data_location_is_deterministic(platform, environment, suffix):
    home = Path('/user')
    expected = Path(suffix) if suffix.startswith('/') else home / suffix
    assert writing_server._workspace_base(platform, home, environment) == expected


def test_portable_preserves_state_and_uses_stable_neutral_cwd(stores, tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES', '')
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'data'))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'data'))
    monkeypatch.setattr(Path, 'home', lambda: tmp_path / 'home')
    (stores / 'AGENTS.md').write_text('project instructions')
    state = stores / '.laplace-state'
    state.mkdir()
    (state / 'existing-receipt').write_bytes(b'previous runtime bytes')
    original = dict(os.environ)
    _, selected = writing_server.configure(stores)
    first = writing_operating.session_workspace('same')
    assert selected == state and (state / 'existing-receipt').read_bytes() == b'previous runtime bytes'
    assert stores not in first.parents
    assert not writing_operating._undeclared_instructions(first)
    writing_server.configure(stores)
    assert writing_operating.session_workspace('same') == first
    another = tmp_path / 'second-checkout'
    another.mkdir()
    (another / 'profiles').mkdir()
    (another / 'registry_projects.json').write_text('{"projects":[]}')
    writing_server.configure(another)
    assert writing_operating.session_workspace('same') != first
    assert writing_server.default_session_workspaces(stores, state) != \
           writing_server.default_session_workspaces(stores, tmp_path / 'another-state')
    assert writing_server.default_session_workspaces(stores, state) != \
           writing_server.default_session_workspaces(tmp_path / 'other-checkout', state)
    # configure writes these selections deliberately; keep test environment isolated.
    for name in ('LAPLACE_REPO_ROOT', 'LAPLACE_WRITING_APP', 'LAPLACE_NO_PREWARM'):
        if name in original: monkeypatch.setenv(name, original[name])
        else: monkeypatch.delenv(name, raising=False)


def test_explicit_cwd_and_ancestor_refusal_are_preserved(stores, monkeypatch):
    _, state = writing_server.configure(stores, session_workspaces=stores / 'bad-cwd')
    (stores / 'AGENTS.md').write_text('must refuse')
    with pytest.raises(ValueError, match='AGENTS.md'):
        writing_operating.session_workspace('bad')


def test_session_symlink_cannot_redirect_provider_cwd_into_checkout(stores):
    base = writing_operating.session_workspace_root()
    base.mkdir()
    (base / 'redirect').symlink_to(stores, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        writing_operating.session_workspace('redirect')


def test_storage_projection_exact_bytes_and_same_http_model(stores):
    body = b'held body bytes'
    digest = 'a' * 64
    path = stores / 'contract/writing_bodies' / digest[:2] / digest
    path.parent.mkdir(parents=True)
    path.write_bytes(body)
    with (stores / 'contract/talk.jsonl').open('a') as stream:
        stream.write(json.dumps({'project': 'one', 'session_id': 'one-cwd',
                                'body': {'content_handle': 'sha256:' + digest}})+'\n')
    (stores / 'projects/one/outside-link').symlink_to(stores / 'contract')
    before = (stores / 'contract/talk.jsonl').read_bytes()
    direct = writing_storage.inspect('one', stores)
    assert direct['bytes']['own_files'] == len(b'unchanged source') + len(b'old version')
    assert direct['bytes']['saved_versions'] == len(b'old version')
    assert direct['bytes']['saved_bodies'] == len(body)
    assert direct['bytes']['conversation'] == len(before.splitlines(keepends=True)[1])
    status, _, response = project_work_surface.handle('/work/storage', {'project': ['one']}, 'GET', repo_root=stores)
    assert status == 200 and json.loads(response)['bytes'] == direct['bytes']
    assert (stores / 'contract/talk.jsonl').read_bytes() == before
    assert len(response) < 2048
    from laplace.native import declarations as writing_declarations
    assert 'storage' in reads.READS and 'storage_prune' in reads.WRITES
    assert operations._execute(stores, 'one', 'work', 'help', {'operation': 'storage'})


def test_prune_keeps_recorded_nonempty_discovery_symlinks_and_active(stores, tmp_path, monkeypatch):
    base = writing_operating.session_workspace_root()
    for name in ('orphan', 'active', 'saved-two', '_discovery', 'nonempty'):
        writing_operating.session_workspace(name)
    (base / 'nonempty/native-history').write_text('provider bytes')
    (base / 'link').symlink_to(tmp_path / 'unrelated', target_is_directory=True)
    monkeypatch.setattr(writing_storage, '_process_cwds', lambda: ([base / 'active'], []))
    before = (stores / 'projects/one/manuscript/source.tex').read_bytes()
    with pytest.raises(ValueError, match='Confirm'):
        writing_storage.prune('one', {}, stores)
    result = writing_storage.prune('one', {'confirm': True}, stores)
    assert result['removed'] == ['orphan']
    assert all((base / name).exists() for name in ('active', 'saved-two', '_discovery', 'nonempty'))
    assert (base / 'link').is_symlink()
    assert (stores / 'projects/one/manuscript/source.tex').read_bytes() == before
    records = [json.loads(line) for line in (stores / 'contract/journal.jsonl').read_text().splitlines()]
    assert records[0]['candidates'] == ['orphan'] and records[-1]['status'] == 'DONE'


def test_unknown_process_or_ledger_never_authorizes_prune(stores, monkeypatch):
    workspace = writing_operating.session_workspace('orphan')
    monkeypatch.setattr(writing_storage, '_process_cwds', lambda: ([], [987654]))
    with pytest.raises(ValueError, match='987654'):
        writing_storage.prune('one', {'confirm': True}, stores)
    (stores / 'contract/talk.jsonl').write_text('{broken row\n')
    with pytest.raises(ValueError):
        writing_storage.prune('one', {'confirm': True}, stores)
    assert workspace.is_dir() and not (stores / 'contract/journal.jsonl').exists()


def test_current_user_unknown_cwd_is_relevant_but_other_uid_is_not(monkeypatch):
    class Process:
        def __init__(self, pid, uid, cwd): self.pid, self.uid, self.directory = pid, uid, cwd
        def uids(self):
            from types import SimpleNamespace
            return SimpleNamespace(real=self.uid)
        def create_time(self): return 123.0
        def status(self): return 'sleeping'
        def cwd(self):
            if self.directory is None: raise writing_storage.psutil.AccessDenied(self.pid)
            return str(self.directory)
    visible = Process(1, 1000, '/known')
    unknown = Process(2, 1000, None)
    other_user = Process(3, 0, None)
    processes = {p.pid: p for p in (visible, unknown, other_user)}
    monkeypatch.setattr(writing_storage.os, 'getuid', lambda: 1000)
    monkeypatch.setattr(writing_storage.psutil, 'process_iter', lambda: iter(processes.values()))
    monkeypatch.setattr(writing_storage.psutil, 'Process', lambda pid: processes[pid])
    active, uncertain = writing_storage._process_cwds()
    assert active == [Path('/known')] and uncertain == [2]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


HARNESS = Path('evidence/WRITING_CONSOLIDATION_2026-10-03/harness2')


def test_direct_fixture_removes_template_duplicate_and_keeps_exact_manifest(tmp_path, monkeypatch):
    measure = _load(HARNESS / '_measure.py', 'resource_measure')
    class TinyHarness:
        @staticmethod
        def build_fixture(source, target, projects):
            target.mkdir(parents=True)
            (target / 'bytes').write_bytes(b'x' * 65536)
            return {'files': 1, 'bytes': 65536, 'projects': projects}
        @staticmethod
        def mint_turn(target, projects):
            (target / 'turn').write_text('same fixture row')
        @staticmethod
        def fixture_turns(projects): return {p: 'fixture-turn' for p in projects}
    monkeypatch.setattr(measure, 'harness', lambda _: TinyHarness)
    cached, old = measure.fixture(tmp_path / 'cached', source=tmp_path, projects=['one'])
    monkeypatch.setenv('LAPLACE_MEASURE_NO_TEMPLATE', '1')
    direct, new = measure.fixture(tmp_path / 'direct', source=tmp_path, projects=['one'])
    assert new == old
    assert {p.name: p.read_bytes() for p in direct.iterdir()} == {p.name: p.read_bytes() for p in cached.iterdir()}
    assert not (tmp_path / 'direct/template').exists()
    assert sum(p.stat().st_size for p in (tmp_path / 'cached').rglob('*') if p.is_file()) > \
           2 * sum(p.stat().st_size for p in (tmp_path / 'direct').rglob('*') if p.is_file())


@pytest.mark.skipif(os.name != 'posix', reason='Bash oracle owns POSIX process groups')
def test_scratch_signal_cleanup_and_concurrent_isolation(tmp_path):
    path = tmp_path / 'owned'
    ready = tmp_path / 'ready'
    command = [sys.executable, str(HARNESS / 'scratch.py'), '--path', str(path), '--',
               sys.executable, '-c', 'import pathlib,time; pathlib.Path('+repr(str(ready))+').touch(); time.sleep(60)']
    first = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    other_path, other_ready = tmp_path / 'independent', tmp_path / 'other-ready'
    other_command = list(command)
    other_command[3] = str(other_path)
    other_command[-1] = other_command[-1].replace(repr(str(ready)), repr(str(other_ready)))
    independent = subprocess.Popen(other_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 5
        while not (ready.exists() and other_ready.exists()) and time.monotonic() < deadline: time.sleep(.03)
        assert ready.exists() and other_ready.exists()
        second = subprocess.run(command, capture_output=True, text=True, timeout=5)
        assert second.returncode == 2 and path.is_dir()
        first.send_signal(signal.SIGTERM)
        stdout, _ = first.communicate(timeout=10)
        assert first.returncode == 143
        assert not path.exists(), stdout
        assert ready.exists()  # evidence-like sibling is never removed
        assert independent.poll() is None and other_path.is_dir()
        independent.send_signal(signal.SIGTERM)
        stdout, _ = independent.communicate(timeout=10)
        assert not other_path.exists(), stdout
    finally:
        if first.poll() is None: first.kill(); first.wait()
        if independent.poll() is None: independent.kill(); independent.wait()


def test_scratch_refuses_existing_unowned_path(tmp_path):
    path = tmp_path / 'unowned'
    path.mkdir()
    (path / 'proof').write_text('retained')
    result = subprocess.run([sys.executable, str(HARNESS / 'scratch.py'), '--path', str(path),
                             '--', sys.executable, '-c', 'pass'], capture_output=True, text=True)
    assert result.returncode == 2 and (path / 'proof').read_text() == 'retained'
