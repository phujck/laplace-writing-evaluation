"""laplace.core runtime family: qualified roots, the bootstrap policy, manifest commands, the watchdog and versioning.

Synthetic fixtures under tmp_path only. The only child processes are the manifest one-liners core.process runs
(`test -f`, `printf`) with a bounded timeout in the fixture directory.
"""
from __future__ import annotations

import importlib.util
import os
import runpy
import time
from pathlib import Path

import pytest

from laplace.core import checkout, process, versioning

SOURCE = Path(__file__).resolve().parents[1]


def test_each_qualified_root_has_its_own_resolver(monkeypatch, tmp_path):
    import laplace
    package = Path(laplace.__file__).resolve().parent   # this checkout's src/laplace, or an installed copy
    assert checkout.package_root() == package and checkout.source_tree() == package.parents[1]
    if package == SOURCE / 'src' / 'laplace':
        assert checkout.source_tree() == SOURCE
    monkeypatch.delenv('LAPLACE_REPO_ROOT', raising=False)
    assert checkout.repo_root() == checkout.source_tree()
    monkeypatch.setenv('LAPLACE_REPO_ROOT', str(tmp_path / 'served'))
    assert checkout.repo_root() == (tmp_path / 'served').resolve() and checkout.source_tree() == package.parents[1]


@pytest.mark.parametrize('value, expected', [(None, 'home'), ('', 'home'), ('   ', 'home'), ('STATE', 'state'), ('~/x-state', 'tilde')])
def test_the_state_home_has_one_rule(monkeypatch, tmp_path, value, expected):
    if value is None:
        monkeypatch.delenv('LAPLACE_STATE', raising=False)
    else:
        monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / value) if value == 'STATE' else value)
    want = {'home': Path.home() / '.mcp-gerard' / 'laplace', 'state': tmp_path / 'STATE', 'tilde': Path.home() / 'x-state'}[expected]
    assert checkout.state_root() == want


def test_a_relocated_package_derives_its_own_tree_and_still_honours_the_configured_checkout(monkeypatch, tmp_path):
    copy = tmp_path / 'elsewhere' / 'src' / 'laplace' / 'core' / 'checkout.py'
    copy.parent.mkdir(parents=True)
    copy.write_bytes((SOURCE / 'src/laplace/core/checkout.py').read_bytes())
    spec = importlib.util.spec_from_file_location('relocated_checkout', copy)
    moved = importlib.util.module_from_spec(spec); spec.loader.exec_module(moved)
    monkeypatch.delenv('LAPLACE_REPO_ROOT', raising=False)
    assert moved.source_tree() == (tmp_path / 'elsewhere').resolve() and moved.package_root() == copy.parent.parent.resolve()
    monkeypatch.setenv('LAPLACE_REPO_ROOT', str(SOURCE))
    assert moved.repo_root() == SOURCE


def test_the_bootstrap_policy_refuses_code_loaded_from_another_checkout(tmp_path):
    """The launcher loads core/runtime.py by path; policy code from one checkout never vouches for another."""
    policy = runpy.run_path(str(SOURCE / 'src/laplace/core/runtime.py'))
    assert policy['_policy_source_tree']() == SOURCE
    other = tmp_path / 'other'
    (other / 'scripts').mkdir(parents=True)
    (other / 'runtime_profiles.toml').write_bytes((SOURCE / 'runtime_profiles.toml').read_bytes())
    with pytest.raises(policy['RuntimePolicyError'], match='runtime policy source is'):
        policy['require_runtime'](other)


def test_a_manifest_command_is_rendered_and_run_for_the_directory_it_runs_in(monkeypatch, tmp_path):
    caller, target = tmp_path / 'caller', tmp_path / 'target'
    (caller / '.venv/bin').mkdir(parents=True); (caller / '.venv/bin/python').write_text('')
    target.mkdir()
    monkeypatch.chdir(caller)   # the caller's process directory has a venv; the command's directory does not
    cmd = '.venv/bin/python -c pass && test -f marker'
    rendered = process.normalize_cmd(cmd, target)
    assert '.venv/bin/python' not in rendered
    assert process.normalize_cmd(cmd, caller) == cmd
    (target / 'marker').write_text('x')
    proc = process.run_manifest_cmd(cmd, target, timeout=60)
    assert proc.rendered == rendered and proc.args == rendered and proc.returncode == 0
    assert process.run_manifest_cmd('printf "%s" "$PWD"', target, timeout=60).stdout == str(target)


def test_a_watchdog_timeout_stops_the_wait_and_cancels_nothing(monkeypatch, tmp_path):
    assert process._ENABLED is False
    monkeypatch.setattr(process, '_ENABLED', True)
    landed = tmp_path / 'landed'

    def work():
        time.sleep(0.4)
        landed.write_text('effect')
        return 'done'

    out = process.guard('slow', 0.05, work)
    assert out['timed_out'] is True and out['cancelled'] is False and 'not cancelled' in out['hint']
    deadline = time.time() + 5
    while not landed.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert landed.read_text() == 'effect'


def test_versioning_commits_only_the_named_paths_and_reverts_exactly(tmp_path):
    repo = tmp_path / 'repo'
    owned, neighbour = repo / 'owned.txt', repo / 'neighbour.txt'
    repo.mkdir(); owned.write_text('one\n'); neighbour.write_text('untouched\n')
    first = versioning.commit(repo, [owned], 'owned one')
    assert first and versioning.head_sha(repo) == first
    owned.write_text('two\n'); neighbour.write_text('neighbour edit\n')
    second = versioning.commit(repo, [owned], 'owned two')
    from dulwich.repo import Repo
    tree = Repo(str(repo))[Repo(str(repo))[second.encode()].tree]
    assert [entry.path for entry in tree.items()] == [b'owned.txt']
    assert versioning.commit(repo, [owned], 'nothing new') is None
    ok, sha = versioning.revert(repo, second)
    assert ok and owned.read_text() == 'one\n' and neighbour.read_text() == 'neighbour edit\n'
    assert versioning.log_paths_since(repo, '1970-01-01T00:00:00+00:00') == {'owned.txt'}
