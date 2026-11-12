"""A pinned Work observation must survive inspection, but never silently rebase."""
import json
import shutil

import pytest

from laplace.web import authoring as controller
from laplace.work import project_work as work
from laplace.writing import records as writing_records
from laplace.writing import turn_admission
from laplace.writing.records import _fold as records_fold
from laplace.writing import turn_jobs
from laplace.writing import session_reads
from laplace.writing import provider as writing_provider
from laplace.core import checkout


@pytest.fixture
def target(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES', str(tmp_path / 'workspaces'))
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()
    work.task('p', {'id': 'parent', 'title': 'Campaign', 'goal': 'Original goal'}, tmp_path)
    work.task('p', {'id': 'required', 'title': 'Check', 'goal': 'Inspect evidence'}, tmp_path)
    work.task('p', {'id': 'local', 'title': 'Local work', 'goal': 'Explain the result',
                    'parent_work_id': 'parent', 'depends_on': ['required']}, tmp_path)
    tasks = work._tasks('p', tmp_path)
    pins = {'expected_work_scope_revision': work._work_basis(tasks, 'local')[0]['scope_revision'],
            'expected_dependency_revision': work._dependency_revision(tasks['local'], tasks)}
    yield tmp_path, pins
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_exact_inspected_scope_is_admitted(target):
    root, pins = target
    context = work.context('p', 'local', root, require_observation=True, **pins)
    assert context['work_basis']['scope_revision'] == pins['expected_work_scope_revision']
    assert context['work_id'] == 'local'


@pytest.mark.parametrize('change', ['missing', 'parent', 'dependency'])
def test_refusal_precedes_any_session_or_provider_effect(target, monkeypatch, change):
    root, pins = target
    if change == 'missing':
        pins = {}
    elif change == 'parent':
        prior = work._tasks('p', root)['parent']
        work.task('p', {'id': 'parent', 'goal': 'Changed containing goal',
                        'expected_work_revision': work._task_revision(prior)}, root)
    else:
        # A new prerequisite acceptance occurrence changes dependency identity
        # even when its scientific description and selected Work are unchanged.
        prior = work._tasks('p', root)['required']
        work._append(root, {**prior, 'record': 'project-work-transition',
                            'status': 'done', 'ts': '2026-10-11T23:00:00Z'})
    before = work._ledger(root).read_bytes()
    monkeypatch.setattr(turn_admission, 'new_session', lambda *a, **kw: pytest.fail('session effect'))
    monkeypatch.setattr(writing_provider, 'WritingTurn', lambda *a, **kw: pytest.fail('provider effect'))
    with pytest.raises(work.WorkConflict) as refusal:
        turn_admission.start_turn(root, {'project': 'p', 'work_id': 'local',
                                    'text': 'Do the inspected work.', **pins})
    assert refusal.value.details['code'] == 'CHANGED_INPUT'
    assert refusal.value.details['field'] == (
        'expected_dependency_revision' if change == 'dependency' else 'expected_work_scope_revision')
    assert refusal.value.details['next_reads'][0]['payload']['id'] == 'local'
    assert work._ledger(root).read_bytes() == before
    assert session_reads._records(root)['sessions'] == {}
    assert session_reads._records(root)['turns'] == {}


def test_http_refusal_keeps_exact_owner_recovery(target, monkeypatch):
    root, _ = target
    monkeypatch.setattr(checkout, 'repo_root', lambda: root)
    status, _, raw = controller.handle('/authoring/turn', {}, 'POST', json.dumps({
        'project': 'p', 'work_id': 'local', 'text': 'An old composer has no observation.'}).encode())
    body = json.loads(raw)
    assert status == 409
    assert body['field'] == 'expected_work_scope_revision'
    assert body['work_id'] == 'local'
    assert body['next_reads'][0]['http']['url'].endswith('view=detail&id=local')


def test_guards_without_work_refuse(target, monkeypatch):
    root, pins = target
    monkeypatch.setattr(turn_admission, 'new_session', lambda *a, **kw: pytest.fail('session effect'))
    with pytest.raises(ValueError, match='explicit work_id'):
        turn_admission.start_turn(root, {'project': 'p', 'text': 'Continue.', **pins})


@pytest.mark.parametrize('ident', [[], {}, '', 42])
def test_malformed_work_identity_refuses_before_effects(target, monkeypatch, ident):
    root, pins = target
    monkeypatch.setattr(turn_admission, 'new_session', lambda *a, **kw: pytest.fail('session effect'))
    with pytest.raises(ValueError, match='nonempty exact Work identity'):
        turn_admission.start_turn(root, {'project': 'p', 'work_id': ident, 'text': 'Continue.', **pins})


def test_accepted_request_retry_keeps_original_admission(target):
    root, _ = target
    writing_records.bank(root, {'record': 'writing-session', 'id': 'session', 'project': 'p', 'role': 'author'})
    writing_records.bank(root, {'record': 'writing-turn', 'id': 'turn', 'session_id': 'session',
                            'project': 'p', 'mode': 'work', 'request_id': 'accepted', 'work_id': 'local'})
    answer = turn_admission.start_turn(root, {'project': 'p', 'work_id': 'local', 'mode': 'work',
                                         'request_id': 'accepted', 'text': 'Retry the accepted request.'})
    assert answer == {'turn_id': 'turn', 'session_id': 'session', 'reused': True}
