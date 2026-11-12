"""Retained controller history belongs to the census, never the scratch remover."""
from __future__ import annotations
import json
from pathlib import Path

from laplace.writing import operating as writing_operating
from laplace.projects import writing_storage
from laplace.writing import session_reads
from laplace.writing import child_hosts


def test_project_controller_bytes_use_existing_owner_without_reading_controls(tmp_path, monkeypatch):
    root, state, cwd = tmp_path / 'checkout', tmp_path / 'runtime', tmp_path / 'provider-cwd'
    root.mkdir()
    (root / 'profiles').mkdir()
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [
        {'name': 'one', 'project_dir': 'projects/one'}, {'name': 'two', 'project_dir': 'projects/two'}]}))
    (root / 'contract').mkdir()
    rows = [{'record': 'writing-session', 'id': 'WS-one', 'project': 'one'},
            {'record': 'writing-session', 'id': 'WS-one-more', 'project': 'two'}]
    (root / 'contract/talk.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    monkeypatch.setenv('LAPLACE_STATE', str(state))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES', str(cwd))
    path = child_hosts._host_path(root, 'WS-one')
    path.parent.mkdir(parents=True)
    path.write_bytes(b'host receipt bytes')
    path.with_suffix('.cancel.json').write_bytes(b'cancel history')
    mailbox = child_hosts._steer_mailbox(root, 'WS-one')
    mailbox.mkdir()
    control = mailbox / '000001.json'
    control.write_bytes(b'control bytes')
    other = child_hosts._host_path(root, 'WS-one-more')
    other.write_bytes(b'other project bytes')
    monkeypatch.setattr(session_reads, '_child_control_rows', lambda *a, **k: (_ for _ in ()).throw(
        AssertionError('byte census must stat existing files, not read/parse control commands')))
    monkeypatch.setattr(writing_storage, '_process_cwds', lambda: ([], []))
    before = {str(p): p.read_bytes() for p in path.parent.rglob('*') if p.is_file()}
    result = writing_storage.inspect('one', root)
    expected = len(b'host receipt bytes')+len(b'cancel history')+len(b'control bytes')
    assert result['bytes']['execution_history'] == expected
    assert writing_storage.inspect('two', root)['bytes']['execution_history'] == len(b'other project bytes')
    assert 'execution receipts and controls' in result['cleanup']['protected']
    writing_operating.session_workspace('orphan')
    writing_storage.prune('one', {'confirm': True}, root)
    assert before == {str(p): p.read_bytes() for p in path.parent.rglob('*') if p.is_file()}


def test_finished_receipt_stays_in_project_census_and_survives_prune(tmp_path, monkeypatch):
    root = tmp_path / 'checkout'; root.mkdir()
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [
        {'name': 'one', 'project_dir': 'projects/one'}, {'name': 'two', 'project_dir': 'projects/two'}]}))
    (root / 'contract').mkdir()
    (root / 'contract/talk.jsonl').write_text(json.dumps(
        {'record': 'writing-session', 'id': 'WS-one', 'project': 'one'})+'\n')
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES', str(tmp_path / 'workspaces'))
    monkeypatch.setattr(writing_storage, '_process_cwds', lambda: ([], []))
    path = child_hosts._host_path(root, 'WS-one')
    child_hosts._write_host(path, {'session_id': 'WS-one', 'turn_id': 'WT-one', 'state': 'RUNNING'})
    child_hosts._finish_child_execution(root, 'WS-one', 'WT-one', 'completed')
    finished = path.parent / 'finished' / path.name
    before = finished.read_bytes()
    assert not path.exists()
    assert writing_storage.inspect('one', root)['bytes']['execution_history'] == len(before)
    assert writing_storage.inspect('two', root)['bytes']['execution_history'] == 0
    writing_storage.prune('one', {'confirm': True}, root)
    assert finished.read_bytes() == before
