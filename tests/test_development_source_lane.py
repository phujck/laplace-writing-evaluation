"""A development lane (wave 13, dev-route packets 1 and 2; incorporation D4, D6), proved on a temporary git repository that
stands in for the serving checkout, with no app, no model and no network.

L1  lane cuts a lean worktree (the real scripts/sparse_worktree.sh, re-rooted at the temporary repository) under a temporary
    lane home, appends the Work's development-lane row and grants the parent session src/**, tests/**, scripts/**, profiles/**
    with every operation, the fixed check profiles and no evaluator; discard revokes the grant and removes the worktree.
L2  basis_checkout is the one resolver: a lane id resolves only from its own Work's latest lane row (ACTIVE, ADOPTED for
    currentness only, DISCARDED unknown); a registered repository resolves as configured.
L3  the fixed profiles (profiles/development_checks.json) run in the isolated check with declared targets, and the check row
    lists the failing names read from the runner's own output.
The live tree stays a protected root: grant, read, candidate and check refuse it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import runtime_guard
from laplace.core import checkout as serving
from laplace.projects import writing_sources
from laplace.web import project_work_surface
from laplace.work import development_source as D, project_work
from test_writing_dispatch import _parent_turn, tree  # noqa: F401

P = 'book'
HERE = Path(__file__).resolve().parents[1]
OK_MJS = "import test from 'node:test';\ntest('adds two numbers', () => {});\n"
BAD_MJS = ("import test from 'node:test';\nimport assert from 'node:assert/strict';\n"
           "test('a deliberately failing case', () => { assert.equal(1, 2); });\ntest('a passing neighbour', () => {});\n")
OK_PY = 'def test_ok():\n    assert 1 + 1 == 2\n'
BAD_PY = 'def test_bad():\n    assert 1 + 1 == 3\n'


def _git(repo: Path, *args) -> str:
    done = subprocess.run([shutil.which('git'), '-C', str(repo), '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', *args],
                          capture_output=True, text=True, check=True)
    return done.stdout.strip()


def _serving_repository(base: Path) -> Path:
    """A small git repository standing in for the serving checkout, holding the real lane cutter re-rooted at itself."""
    repo = base / 'serving'
    for relative, text in {'src/app.py': 'def answer():\n    return 42\n', 'src/data.json': '{"ok": true}\n', 'tests/ok.test.mjs': OK_MJS,
                           'tests/bad.test.mjs': BAD_MJS, 'tests/test_ok.py': OK_PY, 'tests/test_bad.py': BAD_PY, 'README.md': 'serving fixture\n'}.items():
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        (repo / relative).write_text(text)
    script = (HERE / 'scripts/sparse_worktree.sh').read_text()
    assert script.count('ROOT=/home/phujck/VScodeProjects/laplace\n') == 1
    (repo / 'scripts').mkdir()
    (repo / 'scripts/sparse_worktree.sh').write_text(script.replace('ROOT=/home/phujck/VScodeProjects/laplace\n', 'ROOT=%s\n' % repo))
    (repo / 'profiles').mkdir()
    shutil.copyfile(HERE / 'profiles/development_checks.json', repo / 'profiles/development_checks.json')
    for relative in ('runtime_profiles.toml', '.claude/workflows/atlas-wave.js'):     # the node profiles' lane_dependencies
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE / relative, repo / relative)
    _git(repo, 'init', '-q', '-b', 'main')
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-q', '-m', 'base')
    return repo


@pytest.fixture
def lane_root(tree, monkeypatch):
    root = tree
    for name in ('git', 'bash', 'bwrap'):
        found = shutil.which(name)
        if not found:
            pytest.skip('%s is not available on this host' % name)
        runtime_guard.allow_executable(monkeypatch, found)
    repo = _serving_repository(root.parent / (root.name + '-serving'))
    monkeypatch.setattr(serving, 'repo_root', lambda *a, **k: repo)      # the protected serving checkout
    monkeypatch.setattr(serving, 'source_tree', lambda *a, **k: repo)    # the app source a lane is cut from
    monkeypatch.setenv(D.LANE_HOME_ENV, str(root.parent / (root.name + '-lanes')))
    (root / 'profiles').mkdir(exist_ok=True)
    shutil.copyfile(HERE / 'profiles/development_checks.json', root / 'profiles/development_checks.json')
    (root / 'profiles/writing_sources.json').write_text(json.dumps({'repositories': {'live': str(repo)}}))
    lifecycle = Path('~/.local/share/laplace/runtime/python/current/bin/python3.14').expanduser()
    if lifecycle.is_file():
        (root / 'runtime_profiles.toml').write_text('[lifecycle]\npython = "%s"\nexpected_python = "%d.%d.%d"\n' % ((lifecycle,) + tuple(sys.version_info[:3])))
    project_work.task(P, {'id': 'dev', 'title': 'Change the app', 'goal': 'Prove a lane can be cut, checked and discarded'}, root)
    session, _turn = _parent_turn(root)
    yield root, repo, session
    subprocess.run([shutil.which('git'), '-C', str(repo), 'worktree', 'prune'], capture_output=True)


def _door(root: Path, payload: dict) -> dict:
    code, _ctype, body = project_work_surface.handle('/work/development', {}, 'POST', json.dumps({**payload, 'project': P}).encode(), repo_root=root)
    value = json.loads(body)
    if code != 200:
        raise ValueError(value.get('error') or str(value))
    return value


def _task(root: Path) -> dict:
    return project_work._tasks(P, root)['dev']


def _cut(root: Path, session: str) -> dict:
    return _door(root, {'action': 'lane', 'work_id': 'dev', 'expected_work_revision': project_work._task_revision(_task(root)), 'parent_session_id': session})


def test_a_lane_is_cut_granted_to_its_session_and_discarded_with_its_worktree(lane_root):
    root, repo, session = lane_root
    revision = writing_sources.inventory(root)['revision'] if hasattr(writing_sources, 'inventory') else None
    cut = _cut(root, session)
    lane = cut['lane']
    checkout = Path(lane['checkout'])
    assert lane['state'] == 'ACTIVE' and lane['id'] == 'lane:dev' and lane['base'] == _git(repo, 'rev-parse', 'HEAD')
    assert checkout.is_dir() and checkout.is_relative_to(D.lane_home()) and (checkout / 'src/app.py').is_file()
    assert not (checkout / 'README.md').exists()                     # lean: only the code, tests, tools and profiles
    assert _git(repo, 'rev-parse', '--verify', 'refs/heads/' + lane['branch']) == lane['base']
    assert lane['bytes'] > 0 and lane['grants'] == [cut['grant']['id']]
    grant = cut['grant']
    assert grant['repository'] == 'lane:dev' and grant['parent_session_id'] == session and grant['evaluator'] is None
    assert grant['paths'] == list(D.LANE_PATHS) and grant['operations'] == sorted(D.OPERATIONS)
    assert {'node-tests', 'node-suite', 'syntax'} <= set(grant['checks'])
    assert grant['checks']['node-tests']['targets'] == ['tests/*.test.mjs'] and grant['checks']['node-tests']['requires_targets'] is True
    # files the node checks read outside the writable paths are pinned from the cut lane into the existing dependencies map
    for name in ('node-tests', 'node-suite'):
        assert grant['checks'][name]['dependencies'] == {relative: D._pin(checkout / relative) for relative in ('runtime_profiles.toml', '.claude/workflows/atlas-wave.js')}
        assert grant['checks'][name]['runtime'] == D.REGISTERED_RUNTIME and grant['checks'][name]['sandbox_differences'][0]['name'] == 'tests/manuscript_dom.test.mjs'
    # the status read states the lane's own grant: its id, state, paths and operations (the page draws its scope from these)
    assert lane['grant'] == {'id': grant['id'], 'state': 'ACTIVE', 'paths': grant['paths'], 'operations': grant['operations'],
                             'parent_session_id': session, 'expires_at': grant['expires_at'], 'revoked_at': None}
    withheld = {item['name'] for item in lane['profiles_withheld']}
    assert set(grant['checks']) | withheld == set(D.check_profiles(root)['profiles'])
    if revision is not None:
        assert writing_sources.inventory(root)['revision'] == revision    # a lane never enters the configured inventory
    again = _cut(root, session)
    assert again['reused'] is True and again['lane']['branch'] == lane['branch']   # one ACTIVE lane per Work

    status = _door(root, {'action': 'status', 'work_id': 'dev', 'session_id': session})
    assert status['lane']['branch'] == lane['branch'] and status['work'] == {'id': 'dev', 'title': 'Change the app'}
    offers = {(offer['action'], offer.get('name')) for offer in status['offers']}
    assert ('discard', None) in offers and ('check', 'node-tests') in offers and ('lane', None) not in offers
    discard_offer = next(offer for offer in status['offers'] if offer['action'] == 'discard')
    assert discard_offer['request'] == {'action': 'discard', 'work_id': 'dev', 'branch': lane['branch']}
    assert status['lane']['grant']['state'] == 'ACTIVE'

    with pytest.raises(ValueError, match='now'):
        _door(root, {'action': 'discard', 'work_id': 'dev', 'branch': 'app-dev/dev-older'})
    done = _door(root, discard_offer['request'])['lane']
    assert done['state'] == 'DISCARDED' and done['revoked_grants'] == [grant['id']]
    assert done['removal'] == {'worktree': 'REMOVED', 'branch': 'REMOVED'} and not checkout.exists()
    assert D._latest(_task(root), 'grant', grant['id'])['state'] == 'REVOKED'
    with pytest.raises(ValueError, match='UNKNOWN'):
        D.basis_checkout(root, P, 'dev', 'lane:dev', 'operation')
    after = _door(root, {'action': 'status', 'work_id': 'dev', 'session_id': session})
    assert [offer['action'] for offer in after['offers']] == ['lane'] and after['lane']['state'] == 'DISCARDED'
    if revision is not None:
        assert writing_sources.inventory(root)['revision'] == revision


def test_the_resolver_reads_only_its_own_works_latest_lane_row(lane_root):
    root, repo, session = lane_root
    assert D.basis_checkout(root, P, 'dev', 'live', 'grant') == repo.resolve()      # a registered repository: as configured
    with pytest.raises(ValueError, match='no lane has been cut'):
        D.basis_checkout(root, P, 'dev', 'lane:dev', 'grant')
    lane = _cut(root, session)['lane']
    assert D.basis_checkout(root, P, 'dev', 'lane:dev', 'operation') == Path(lane['checkout'])
    with pytest.raises(ValueError, match='another Work'):
        D.basis_checkout(root, P, 'dev', 'lane:other', 'operation')
    row = D.lane_row(_task(root))
    project_work._append(root, {**row, 'state': 'ADOPTED', 'ts': D._now(), 'adoption_commit': lane['base']})
    assert D.basis_checkout(root, P, 'dev', 'lane:dev', 'currentness') == repo.resolve()
    with pytest.raises(ValueError, match='currentness only'):
        D.basis_checkout(root, P, 'dev', 'lane:dev', 'operation')
    D._remove_lane(row)


def test_the_live_tree_stays_a_protected_root_for_lanes_grants_and_operations(lane_root, monkeypatch):
    root, repo, session = lane_root
    guard = project_work._task_revision(_task(root))
    with pytest.raises(ValueError, match='never a development resource'):   # a grant on the serving checkout itself
        _door(root, {'action': 'grant', 'request_id': 'grant-live-1', 'work_id': 'dev', 'expected_work_revision': guard, 'repository': 'live',
                     'parent_session_id': session, 'evaluator': 'none', 'paths': ['src/**'], 'operations': ['read']})
    monkeypatch.setenv(D.LANE_HOME_ENV, str(repo / 'lanes'))                 # a lane home inside the serving checkout
    with pytest.raises(ValueError, match='never a development resource'):
        _cut(root, session)
    assert not (repo / 'lanes').exists() and D.lane_row(_task(root)) is None
    monkeypatch.delenv(D.LANE_HOME_ENV)
    monkeypatch.setenv(D.LANE_HOME_ENV, str(root.parent / (root.name + '-lanes')))
    cut = _cut(root, session)
    forged = {**D._latest(_task(root), 'grant', cut['grant']['id']), 'checkout': str(repo)}   # a grant row pointed at the live tree
    project_work._append(root, forged)
    for payload in ({'action': 'read', 'grant_id': forged['id'], 'path': 'src/app.py'},
                    {'action': 'candidate', 'grant_id': forged['id'], 'files': [{'path': 'src/app.py', 'before_sha256': None, 'content': 'x = 1\n'}]},
                    {'action': 'check', 'grant_id': forged['id'], 'name': 'syntax', 'targets': ['src/app.py']}):
        with pytest.raises(ValueError, match='never a development resource'):
            _door(root, payload)
    assert (repo / 'src/app.py').read_text() == 'def answer():\n    return 42\n'
    D._remove_lane(D.lane_row(_task(root)))


def test_fixed_profiles_run_with_declared_targets_and_list_the_failing_names(lane_root):
    root, repo, session = lane_root
    cut = _cut(root, session)
    grant = cut['grant']['id']
    with pytest.raises(ValueError, match='names the files to run'):
        _door(root, {'action': 'check', 'grant_id': grant, 'name': 'node-tests'})
    with pytest.raises(ValueError, match='does not match'):
        _door(root, {'action': 'check', 'grant_id': grant, 'name': 'node-tests', 'targets': ['src/app.py']})
    with pytest.raises(ValueError, match='takes no targets'):
        _door(root, {'action': 'check', 'grant_id': grant, 'name': 'node-suite', 'targets': ['tests/ok.test.mjs']})

    syntax = _door(root, {'action': 'check', 'grant_id': grant, 'name': 'syntax', 'targets': ['src/app.py', 'src/data.json']})['check']
    assert syntax['state'] == 'COMPLETE' and syntax['targets'] == ['src/app.py', 'src/data.json'] and 'STAGED_PYTHON_JSON_SYNTAX_ONLY' in syntax['stdout_tail']

    node = _door(root, {'action': 'check', 'grant_id': grant, 'name': 'node-tests', 'targets': ['tests/ok.test.mjs', 'tests/bad.test.mjs']})['check']
    assert node['state'] == 'FAILED', node.get('stdout_tail')
    assert 'a deliberately failing case' in node['failing'] and 'a passing neighbour' not in node['failing'] and node['failing_complete'] is True
    assert 'adds two numbers' not in node['failing']

    suite = _door(root, {'action': 'check', 'grant_id': grant, 'name': 'node-suite'})['check']
    assert suite['state'] == 'FAILED' and 'a deliberately failing case' in suite['failing'], suite.get('stdout_tail')

    if 'python-tests' in cut['grant']['checks']:
        python = _door(root, {'action': 'check', 'grant_id': grant, 'name': 'python-tests', 'targets': ['tests/test_ok.py', 'tests/test_bad.py']})['check']
        assert python['state'] == 'FAILED' and python['failing'] == ['tests/test_bad.py::test_bad'], python.get('stdout_tail')

    status = _door(root, {'action': 'status', 'work_id': 'dev', 'session_id': session, 'limit': 8})
    listed = status['development']['checks']['items']
    assert [row['name'] for row in listed[:2]] == ['node-suite', 'node-tests'] or listed[0]['name'] == 'python-tests'   # newest first
    by_name = {row['name']: row for row in listed}
    assert by_name['node-tests']['failing'] == node['failing'] and by_name['syntax']['targets'] == ['src/app.py', 'src/data.json']
    D._remove_lane(D.lane_row(_task(root)))


def test_a_profile_whose_lane_dependency_is_missing_is_withheld_and_declared_differences_reach_the_check_row(lane_root):
    root, repo, session = lane_root
    path = root / 'profiles/development_checks.json'
    value = json.loads(path.read_text())
    value['profiles']['node-suite']['lane_dependencies'] = ['docs/not-in-any-lane.md']
    value['profiles']['node-tests']['profile']['sandbox_differences'] = [{'name': 'a deliberately failing case', 'cause': 'fixture'},
                                                                         {'name': 'adds two numbers', 'cause': 'fixture'}]
    path.write_text(json.dumps(value))
    cut = _cut(root, session)
    assert 'node-suite' not in cut['grant']['checks']
    assert {'name': 'node-suite', 'reason': 'its read-only dependency docs/not-in-any-lane.md is not in the lane'} in cut['lane']['profiles_withheld']
    node = _door(root, {'action': 'check', 'grant_id': cut['grant']['id'], 'name': 'node-tests', 'targets': ['tests/ok.test.mjs', 'tests/bad.test.mjs']})['check']
    assert node['sandbox_differences'] == [{'name': 'a deliberately failing case', 'cause': 'fixture', 'failed': True},
                                           {'name': 'adds two numbers', 'cause': 'fixture', 'failed': False}]
    discarded = _door(root, {'action': 'discard', 'work_id': 'dev', 'branch': cut['lane']['branch']})['lane']
    assert discarded['grant']['state'] == 'REVOKED' and discarded['grant']['revoked_at']     # the read follows the grant


def test_failing_names_come_only_from_the_runner_output():
    tap = b'TAP version 13\n# Subtest: x\n    not ok 1 - inner case\n    ok 2 - fine\nnot ok 1 - tests/x.test.mjs\nnot ok 2 - later # TODO not yet\nnot ok 3 - skipped # SKIP\n'
    assert D._failing('tap', tap, False) == {'failing': ['inner case', 'tests/x.test.mjs'], 'failing_total': 2, 'failing_complete': True}
    pytest_out = b'..F\nFAILED tests/test_a.py::test_x - assert 1 == 2\nERROR tests/test_b.py::test_y\n1 failed\n'
    assert D._failing('pytest', pytest_out, True) == {'failing': ['tests/test_a.py::test_x', 'tests/test_b.py::test_y'], 'failing_total': 2, 'failing_complete': False}
    assert D._failing(None, tap, False) == {}


def test_a_staged_file_stays_read_only_and_keeps_its_executable_bit(tmp_path):
    plain, tool = tmp_path / 'plain.txt', tmp_path / 'tool'
    plain.write_text('x'); tool.write_text('#!/bin/sh\n'); tool.chmod(0o755)
    assert D._staged_mode(plain) == 0o444 and D._staged_mode(tool) == 0o555     # never writable; ./scripts/laplace-python still runs
