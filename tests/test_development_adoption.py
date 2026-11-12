"""Adopt (wave 13, dev-route packet 5; wave10/incorporation.md 'Adoption', D5; ruling D6), proved on a temporary git
repository that stands in for the live tree, with a real lean lane cut from it, real sandboxed checks, no app and no model.

A1  preview is read-only: the diff by file, the checks whose staged pins equal the lane files, the newly failing names
    against the same check on a scratch copy of live HEAD (removed before it returns) and the adopt offer or its refusals.
A2  adopt, at the human door only, under the dispatch and publication locks taken without waiting: one local commit with a
    Work-Id trailer, the lane ADOPTED, its grants revoked, its worktree removed; refused when the live tree moved, when a
    lock is held and when a check is newly failing.
A3  review standing of the adopted basis (D5): current after Adopt and after an unrelated commit, stale after a reviewed-file
    edit and after a reset that drops the adoption commit; the live root is never written by grant, apply or check.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from laplace.representation import source_publication as SP
from laplace.work import development_adoption as A, development_source as D, project_work, project_work_continuity
from test_development_source_lane import P, BAD_MJS, _cut, _door, _git, _task, lane_root  # noqa: F401
from test_writing_dispatch import tree  # noqa: F401

NEW_APP = 'def answer():\n    return 43\n'
FAILING_OK = "import test from 'node:test';\nimport assert from 'node:assert/strict';\ntest('adds two numbers', () => { assert.equal(1 + 1, 3); });\n"
TARGETS = ['tests/ok.test.mjs', 'tests/bad.test.mjs']


def _change(root, grant, path, content):
    lane = D.lane_row(_task(root))
    before = D._pin(Path(lane['checkout']) / path)
    cand = _door(root, {'action': 'candidate', 'grant_id': grant, 'files': [{'path': path, 'before_sha256': before, 'content': content}]})
    effect = _door(root, {'action': 'apply', 'candidate_id': cand['candidate_id']})
    assert effect['effect']['state'] == 'COMMITTED'
    return cand['candidate_id']


def _laned(lane_root, path='src/app.py', content=NEW_APP):
    root, repo, session = lane_root
    _git(repo, 'config', 'user.name', 'fixture author')
    _git(repo, 'config', 'user.email', 'fixture@example.invalid')
    (repo / '.gitignore').write_text('*.lock\n')     # as the live repository's .gitignore:174 (the owner's write leases)
    _git(repo, 'add', '.gitignore')
    _git(repo, 'commit', '-qm', 'ignore lock files')
    cut = _cut(root, session)
    grant = cut['grant']['id']
    candidate = _change(root, grant, path, content)
    check = _door(root, {'action': 'check', 'grant_id': grant, 'name': 'node-tests', 'targets': TARGETS})['check']
    return root, repo, session, cut, grant, candidate, check


def _adopt_request(preview):
    [offer] = preview['offers']
    assert offer['action'] == 'adopt'
    return offer


def test_adopt_review_current(lane_root):
    root, repo, session, cut, grant, candidate, check = _laned(lane_root)
    assert check['state'] == 'FAILED' and check['failing'] == ['a deliberately failing case']
    assert _git(repo, 'status', '--porcelain') == '', 'grant, candidate, apply and check never wrote the live root'
    base = _git(repo, 'rev-parse', 'HEAD')
    after = D._pin(Path(cut['lane']['checkout']) / 'src/app.py')
    basis = D.prepare_review_basis(root, P, 'dev', {'grant_id': grant, 'candidate_id': candidate}, {'src/app.py': after}, door={'origin': 'human'})
    preview = _door(root, {'action': 'preview', 'work_id': 'dev', 'session_id': session})
    shown = preview['preview']
    assert [(f['path'], f['change'], f['flagged'], f['added'], f['removed']) for f in shown['files']] == [('src/app.py', 'modified', False, 1, 1)]
    [row] = shown['checks']
    assert row['id'] == check['id'] and row['current'] is True
    # the failing name fails on the live commit too: it is not newly failing
    assert row['base']['state'] == 'FAILED' and row['newly'] == {'known': True, 'names': [], 'total': 0, 'base_failing_total': 1, 'lane_failing_total': 1}
    assert shown['applies'] is True and shown['scratch']['removed'] is True and shown['live_head'] == base
    offer = _adopt_request(preview)
    assert offer['refused'] == [] and set(offer['request']) == {'action', 'work_id', 'branch', 'preview_id', 'preview_sha256'}
    assert _git(repo, 'status', '--porcelain') == '', 'the preview wrote nothing in the live root'
    done = _door(root, offer['request'])
    commit = done['adoption']['commit']
    assert done['adoption']['state'] == 'COMMITTED' and _git(repo, 'rev-parse', 'HEAD') == commit
    assert _git(repo, 'rev-parse', commit + '^') == base
    message = _git(repo, 'log', '-1', '--format=%B')
    assert 'Work-Id: dev' in message and 'Adoption-Id: ' + done['adoption']['id'] in message
    assert (repo / 'src/app.py').read_text() == NEW_APP and _git(repo, 'status', '--porcelain') == ''
    assert _git(repo, 'show', '--name-only', '--format=', commit) == 'src/app.py'
    lane = D.lane_row(_task(root))
    assert lane['state'] == 'ADOPTED' and lane['removal']['worktree'] == 'REMOVED' and not Path(lane['checkout']).exists()
    assert {row['state'] for row in D._latest_per_id(D.rows(_task(root), 'grant'))} == {'REVOKED'}
    assert A.closeout(_task(root))['state'] == 'COMMITTED' and A.closeout(_task(root))['commit'] == commit
    head = project_work_continuity.closeout(_task(root), {})
    assert head['adoption']['commit'] == commit
    assert D.validate_review_basis(root, P, 'dev', basis, consumed_pins={'src/app.py': after})['status'] == 'CURRENT'
    # the adoption read states the same commit; a repeated Adopt answers the recorded one
    assert _door(root, {'action': 'adoption', 'work_id': 'dev'})['adoption']['commit'] == commit
    assert _door(root, offer['request'])['already'] == 'ADOPTED'


def _adopted(lane_root):
    root, repo, session, cut, grant, candidate, _check = _laned(lane_root)
    after = D._pin(Path(cut['lane']['checkout']) / 'src/app.py')
    basis = D.prepare_review_basis(root, P, 'dev', {'grant_id': grant, 'candidate_id': candidate}, {'src/app.py': after}, door={'origin': 'human'})
    done = _door(root, _adopt_request(_door(root, {'action': 'preview', 'work_id': 'dev'}))['request'])
    return root, repo, basis, after, done['adoption']['commit']


def test_adopted_review_current_after_unrelated_commit(lane_root):
    root, repo, basis, after, commit = _adopted(lane_root)
    (repo / 'README.md').write_text('a later unrelated change\n')
    _git(repo, 'commit', '-qam', 'unrelated')
    assert _git(repo, 'merge-base', '--is-ancestor', commit, 'HEAD') == ''
    assert D.validate_review_basis(root, P, 'dev', basis, consumed_pins={'src/app.py': after})['status'] == 'CURRENT'


def test_adopted_review_stale_after_reviewed_file_edit(lane_root):
    root, repo, basis, after, _commit = _adopted(lane_root)
    (repo / 'src/app.py').write_text('def answer():\n    return 44\n')
    edited = D.validate_review_basis(root, P, 'dev', basis, consumed_pins={'src/app.py': after})
    assert edited['status'] == 'CHANGED' and edited['reason'] == 'consumed source bytes changed'
    _git(repo, 'commit', '-qam', 'edit the reviewed file')
    assert D.validate_review_basis(root, P, 'dev', basis, consumed_pins={'src/app.py': after})['status'] == 'CHANGED'


def test_reset_dropping_the_adoption_commit_reads_stale(lane_root):   # incorporation: test_adopted_review_stale_after_reset
    root, repo, basis, after, commit = _adopted(lane_root)
    _git(repo, 'reset', '-q', '--hard', commit + '^')
    dropped = D.validate_review_basis(root, P, 'dev', basis, consumed_pins={'src/app.py': after})
    assert dropped == {'status': 'CHANGED', 'reason': 'the adoption commit is no longer in live history', 'observed_pins': {}}


def test_grant_still_refuses_live_root(lane_root):
    root, repo, basis, after, _commit = _adopted(lane_root)
    with pytest.raises(ValueError, match='never a development resource'):
        _door(root, {'action': 'grant', 'request_id': 'live-after-adopt', 'work_id': 'dev', 'expected_work_revision': project_work._task_revision(_task(root)),
                     'repository': 'live', 'parent_session_id': lane_root[2], 'evaluator': 'none', 'paths': ['src/**'], 'operations': ['read']})
    with pytest.raises(ValueError, match='read for currentness only'):
        D.basis_checkout(root, P, 'dev', 'lane:dev', 'operation')
    assert _git(repo, 'status', '--porcelain') == ''


def test_adopt_refuses_when_the_live_tree_moved(lane_root):
    root, repo, session, *_ = _laned(lane_root)
    preview = _door(root, {'action': 'preview', 'work_id': 'dev'})
    offer = _adopt_request(preview)
    (repo / 'README.md').write_text('the live tree moved\n')
    _git(repo, 'commit', '-qam', 'moved')
    with pytest.raises(ValueError, match='The live tree has moved to .* since the lane was cut .* Discard this lane and cut a new one'):
        _door(root, offer['request'])
    again = _door(root, {'action': 'preview', 'work_id': 'dev'})
    assert again['offers'][0]['request'] is None and 'The live tree has moved' in again['offers'][0]['refused'][0]
    assert D.lane_row(_task(root))['state'] == 'ACTIVE' and (repo / 'src/app.py').read_text() != NEW_APP


def _held(enter):
    """Hold a lock in another thread (another holder: FileLock is per thread) until released."""
    held, release = threading.Event(), threading.Event()

    def run():
        with enter():
            held.set(); release.wait(10)
    thread = threading.Thread(target=run, daemon=True); thread.start(); assert held.wait(10)
    return release, thread


def test_dispatch_lock_held_refuses_adopt_at_once(lane_root):
    _lock_held_refuses(lane_root, 'dispatch')


def test_publication_lock_held_refuses_adopt_at_once(lane_root):
    _lock_held_refuses(lane_root, 'publication')


def _lock_held_refuses(lane_root, which):
    import time
    root, repo, *_ = _laned(lane_root)
    offer = _adopt_request(_door(root, {'action': 'preview', 'work_id': 'dev'}))
    release, thread = _held(lambda: project_work.dispatch_lock(root) if which == 'dispatch' else SP.publication_lock(root))
    try:
        started = time.perf_counter()
        with pytest.raises(ValueError) as refused:
            _door(root, offer['request'])
        assert str(refused.value) == A.LOCK_REFUSAL[which] and time.perf_counter() - started < 5
    finally:
        release.set(); thread.join(10)
    assert D.lane_row(_task(root))['state'] == 'ACTIVE' and _git(repo, 'status', '--porcelain') == ''
    assert _door(root, offer['request'])['adoption']['state'] == 'COMMITTED'


def test_a_newly_failing_check_refuses_adopt(lane_root):
    root, repo, *_ = _laned(lane_root, 'tests/ok.test.mjs', FAILING_OK)
    preview = _door(root, {'action': 'preview', 'work_id': 'dev'})
    [row] = preview['preview']['checks']
    assert row['newly']['names'] == ['adds two numbers'] and row['newly']['total'] == 1
    offer = _adopt_request(preview)
    assert offer['request'] is None and 'node-tests has 1 newly failing test; Adopt refuses while a check is newly failing.' in offer['refused']
    # a forged request naming the facts' own digest is still refused: Adopt re-derives the facts and their refusal under its locks
    _shown, facts, digest = A._observe(root, P, _task(root), D.lane_row(_task(root)))
    assert facts['refusals'] == offer['refused'] and _shown['id'] == preview['preview']['id']
    forged = {'action': 'adopt', 'work_id': 'dev', 'branch': D.lane_row(_task(root))['branch'], 'preview_id': preview['preview']['id'], 'preview_sha256': digest}
    with pytest.raises(ValueError, match='Adopt refuses: .*node-tests has 1 newly failing test'):
        _door(root, forged)
    assert _git(repo, 'status', '--porcelain') == ''


def _files(root):
    return sorted(str(path.relative_to(root)) for path in Path(root).rglob('*') if path.is_file())


def _scratch_dirs():
    import tempfile
    return sorted(Path(tempfile.gettempdir()).glob('laplace-adopt-*'))


def test_previews_then_adopt_retain_nothing(lane_root):
    _previews_retain_nothing(lane_root, 'adopt')


def test_previews_then_discard_retain_nothing(lane_root):
    _previews_retain_nothing(lane_root, 'discard')


def _previews_retain_nothing(lane_root, ending):
    """judge wave13b adopt r1 'preview-holder': N previews followed by Adopt, or by Discard, leave zero retained files."""
    root, repo, *_ = _laned(lane_root)
    before, scratch_before = _files(root), _scratch_dirs()
    offers = [_adopt_request(_door(root, {'action': 'preview', 'work_id': 'dev'})) for _ in range(3)]
    assert _files(root) == before, 'a preview wrote a file under the Work root'
    assert _scratch_dirs() == scratch_before and _git(repo, 'status', '--porcelain') == ''
    assert len({offer['request']['preview_sha256'] for offer in offers}) == 1, 'the same lane and live tree give the same facts'
    if ending == 'adopt':
        assert _door(root, offers[-1]['request'])['adoption']['state'] == 'COMMITTED'
        assert D.lane_row(_task(root))['state'] == 'ADOPTED'
    else:
        _door(root, {'action': 'discard', 'work_id': 'dev', 'branch': D.lane_row(_task(root))['branch']})
        assert D.lane_row(_task(root))['state'] == 'DISCARDED'
    retained = [name for name in _files(root) if name not in before and Path(name).name.startswith('DP-')]
    assert retained == [] and not (Path(root) / 'contract/development_adoption').exists() and _scratch_dirs() == scratch_before


def test_a_lane_change_after_preview_refuses_the_stale_offer(lane_root):
    root, _repo, _session, _cut_, grant, _cand, _check = _laned(lane_root)
    offer = _adopt_request(_door(root, {'action': 'preview', 'work_id': 'dev'}))
    _door(root, {'action': 'check', 'grant_id': grant, 'name': 'node-tests', 'targets': TARGETS[:1]})
    with pytest.raises(ValueError, match='no longer what the preview showed|Adopt refuses: '):
        _door(root, offer['request'])
    assert D.lane_row(_task(root))['state'] == 'ACTIVE'


def test_a_lane_change_after_its_check_needs_the_check_again(lane_root):
    root, _repo, _session, _cut_, grant, _cand, _check = _laned(lane_root)
    _change(root, grant, 'src/data.json', '{"ok": false}\n')
    offer = _adopt_request(_door(root, {'action': 'preview', 'work_id': 'dev'}))
    assert offer['request'] is None and 'The lane files changed after the node-tests check; run it again.' in offer['refused']


def test_the_native_door_is_refused(lane_root):
    root, *_ = _laned(lane_root)
    with pytest.raises(ValueError, match='only by the author at the human door'):
        A.adopt(root, P, {'action': 'adopt', 'work_id': 'dev', 'branch': 'b', 'preview_id': 'DP-' + '0' * 24, 'preview_sha256': 'sha256:' + '0' * 64},
                {'origin': 'native', 'turn_id': 'T'})


def test_the_carry_preview_names_inputs_that_pin_a_changed_file(monkeypatch, tmp_path):
    reference = lambda *paths: {'exact_descent': {'reference': json.dumps({'source_inputs': [{'path': p, 'sha256': 'sha256:' + '1' * 64} for p in paths]})}}
    carry = {'currentness': {'OP-A': {'state': 'CURRENT', 'reason': 'every pinned file has its retained bytes'}, 'OP-B': {'state': 'CARRIED', 'reason': 'carried'}},
             'leaves': {'OP-A': reference('src/app.py', 'src/other.py'), 'OP-B': reference('src/other.py')}}
    from laplace.engine import source_kernel_input as SKI
    monkeypatch.setattr(SP, 'selections', lambda root: {'inputs': [1]})
    monkeypatch.setattr(SP, 'current', lambda root: {})
    monkeypatch.setattr(SKI, 'close_inputs', lambda root, inputs, parent: carry)
    shown = A._carry_preview(tmp_path, [{'path': 'src/app.py'}])
    assert shown['inputs_total'] == 2 and shown['inputs'] == [{'node_id': 'OP-A', 'today': 'CURRENT', 'today_reason': 'every pinned file has its retained bytes', 'changed_files': ['src/app.py']}]
    monkeypatch.setattr(SP, 'selections', lambda root: None)
    assert A._carry_preview(tmp_path, [{'path': 'src/app.py'}])['note'] == 'This root records no publication inputs, so the close carries none.'
