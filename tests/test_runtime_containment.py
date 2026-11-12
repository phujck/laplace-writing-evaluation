"""Runtime containment (runtime fixture correction, 2026-10-19; Sol RF-1).

The guard denies a provider launch by name or absolute path, a shell and the network before anything starts, in the
parent and in a child host; a child whose bootstrap misbinds the deterministic stub is refused at the provider
boundary before any CLI launch, its turn ends with an explicit failure, and the owned host is cleaned up.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

import runtime_guard
from laplace.web import authoring as authoring_surface
from laplace.writing import provider as writing_provider
from laplace.writing import child_hosts, records, turn_jobs
from test_writing_dispatch import CATALOGUE, tree  # noqa: F401  (tree arms the guard and binds the stub)
from test_writing_dispatch_lifecycle import _plan, _planned, _wait


def test_the_guard_denies_provider_shell_and_network_before_any_launch(tree, monkeypatch):
    for argv in (['claude', '--print', 'x'], ['/usr/local/bin/claude', '--print', 'x'], ['/usr/bin/codex', 'exec'], ['/bin/sh', '-c', 'true']):
        with pytest.raises(RuntimeError, match='runtime guard: subprocess.Popen denied'):
            subprocess.Popen(argv)
    with pytest.raises(RuntimeError, match='runtime guard: os.system denied'):
        os.system('true')
    with pytest.raises(RuntimeError, match='runtime guard: socket.getaddrinfo denied'):
        socket.getaddrinfo('example.invalid', 443)
    with pytest.raises(RuntimeError, match='runtime guard: open denied'):
        open(runtime_guard.MAIN_ROOT + '/contract/talk.jsonl', 'a')
    assert [d['event'] for d in runtime_guard.DENIALS[-7:]] == ['subprocess.Popen'] * 4 + ['os.system', 'socket.getaddrinfo', 'open']
    # the owned Python recipe is the one allowed launch
    sleeper = subprocess.Popen([sys.executable, '-S', '-c', 'import time; time.sleep(0.1)'])
    assert sleeper.wait(timeout=5) == 0


def test_the_fixture_refuses_to_admit_children_on_the_real_provider(tree, monkeypatch):
    stub = writing_provider.WritingTurn
    assert not stub.__module__.startswith('laplace.')
    monkeypatch.setattr(writing_provider, 'WritingTurn', _RealLike)
    with pytest.raises(AssertionError, match='bind the deterministic stub at the runtime lookup'):
        runtime_guard.assert_stub_bound()
    monkeypatch.setattr(writing_provider, 'WritingTurn', stub)
    runtime_guard.assert_stub_bound()


class _RealLike:
    __module__ = 'laplace.writing.provider'


def test_a_misbound_child_host_is_refused_at_the_provider_boundary_before_any_cli_launch(tree, monkeypatch):
    root = tree
    runtime = root / 'misbound-runtime';runtime.mkdir()
    # the child boots the guard and the capability stub, but deliberately leaves writing_provider.WritingTurn real
    (runtime / 'sitecustomize.py').write_text(runtime_guard.BOOTSTRAP + '''
import json
from laplace.writing import provider as wp
from test_writing_dispatch import CATALOGUE
wp.capabilities = lambda *a, **k: json.loads(json.dumps(CATALOGUE))
wp.context_window_advertised = lambda *a, **k: None
''')
    tests = Path(__file__).resolve().parent;source = Path(authoring_surface.__file__).resolve().parents[1]
    log = root / 'guard-denials.jsonl'
    monkeypatch.setenv('PYTHONPATH', os.pathsep.join(map(str, [runtime, source, tests])))
    monkeypatch.setenv('LAPLACE_STATE', str(root / 'state'));monkeypatch.setenv('LAPLACE_GUARD_TESTS', str(tests));monkeypatch.setenv('LAPLACE_GUARD_LOG', str(log))
    monkeypatch.setattr(turn_jobs, '_CHILD_HOST', False)   # a real one-shot host process, as in operation
    parent, ident = _planned(root, _plan(root))   # the carrier's own worker/judge/synthesis shape, unchanged
    from laplace.writing import dispatch_execution
    started = dispatch_execution.launch_dispatch(root, 'book', parent, {'id': ident})
    assert started['started'] is True and started['children']
    child = started['children'][0]
    reply = _wait(lambda: (records.fold_records(root)['turns'].get(child['turn_id']) or {}).get('reply'), seconds=40)
    assert reply['status'] == 'failed', reply
    denials = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    assert denials and denials[0]['event'] == 'subprocess.Popen' and 'claude' in json.dumps(denials[0]['detail']), denials
    assert 'runtime guard' in json.dumps(reply), 'the child\'s own failure names the denial, not a provider answer'
    _wait(lambda: not [h for h in child_hosts.active_child_hosts(root) if h.get('state') in {'STARTING', 'RUNNING', 'WAITING'}], seconds=20)
