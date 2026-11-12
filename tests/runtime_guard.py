"""FAIL-CLOSED CONTAINMENT for runtime tests (runtime fixture correction, 2026-10-19; Sol RF-1).

A runtime test may start owned Python processes (the one-shot child host `python -m laplace.native.tools
--start-child-turn`, the fixture sleeper) and nothing else: no provider binary by name or absolute path, no shell,
no network, no canonical Main or user state. The guard is a Python audit hook installed once per process; the parent
arms it for the duration of a runtime fixture (``arm``), and every child host boots it through ``sitecustomize``
before any application import (``BOOTSTRAP``). Denials raise before the launch and are recorded (``DENIALS`` in the
parent; ``LAPLACE_GUARD_LOG`` in a child). ``assert_stub_bound`` refuses to admit children while the actual runtime
lookup (``writing_provider.WritingTurn``) is still the real provider. Test fixtures only: no production flag.
"""
from __future__ import annotations

import os
import sys

DENIALS: list = []
ARMED = False
MAIN_ROOT = '/home/phujck/VScodeProjects/laplace'
USER_STATE = os.path.expanduser('~/.mcp-gerard')
_INTERPRETER = os.path.realpath(sys.executable)
_INSTALLED = False


#: fixture-local allowances beyond the exact interpreter: the trusted isolation launcher (bubblewrap) for the development
#: check supervisor, armed by `allow_executable` for one test only; provider binaries, shells and the network stay denied
ALLOWED_EXECUTABLES: set = set()


def _executable_allowed(path) -> bool:
    try:
        real = os.path.realpath(str(path))
    except (TypeError, ValueError):
        return False
    return real == _INTERPRETER or real in ALLOWED_EXECUTABLES


def allow_executable(monkeypatch, path) -> None:
    """Allow ONE exact executable (by real path) for the duration of a test; never a directory, never a pattern."""
    monkeypatch.setattr(sys.modules[__name__], 'ALLOWED_EXECUTABLES', set(ALLOWED_EXECUTABLES) | {os.path.realpath(str(path))})


def _deny(event, detail):
    DENIALS.append({'event': event, 'detail': detail})
    log = os.environ.get('LAPLACE_GUARD_LOG')
    if log:
        import json
        with open(log, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps({'event': event, 'detail': detail, 'pid': os.getpid()}) + '\n')
    raise RuntimeError('runtime guard: %s denied: %s' % (event, detail))


def _hook(event, args):
    if not ARMED:
        return
    if event == 'subprocess.Popen':
        executable, argv = args[0], args[1]
        head = executable or (argv[0] if argv else None)
        if not _executable_allowed(head):
            _deny(event, {'executable': str(head), 'argv': [str(a) for a in (argv or [])][:6]})
    elif event in ('os.posix_spawn', 'os.exec'):
        if not _executable_allowed(args[0]):
            _deny(event, {'path': str(args[0])})
    elif event in ('os.system', 'os.spawn'):
        _deny(event, {'command': str(args[0])[:200]})
    elif event in ('socket.connect', 'socket.getaddrinfo', 'socket.gethostbyname', 'socket.sendto', 'socket.sendmsg', 'urllib.Request'):
        _deny(event, {'args': [str(a)[:120] for a in args][:3]})
    elif event == 'open':
        path = str(args[0]) if args and args[0] is not None else ''
        if path.startswith(MAIN_ROOT + '/') or path.startswith(USER_STATE + '/'):
            _deny(event, {'path': path, 'mode': str(args[1]) if len(args) > 1 else ''})


def install() -> None:
    global _INSTALLED
    if not _INSTALLED:
        sys.addaudithook(_hook)
        _INSTALLED = True


def arm(monkeypatch) -> None:
    """Arm the guard for one test (the hook stays installed; it is inert while disarmed)."""
    install()
    monkeypatch.setattr(sys.modules[__name__], 'ARMED', True)
    monkeypatch.setenv('LAPLACE_GUARD_LOG', os.environ.get('LAPLACE_GUARD_LOG') or os.path.join(os.environ.get('LAPLACE_STATE') or '/tmp', 'guard-denials.jsonl'))


def assert_stub_bound() -> None:
    """Refuse to admit children while the actual runtime lookup is still the real provider."""
    from laplace.writing import provider as writing_provider
    cls = writing_provider.WritingTurn
    if (getattr(cls, '__module__', '') or '').startswith('laplace.'):
        raise AssertionError('writing_provider.WritingTurn is the real provider %r: bind the deterministic stub at the runtime lookup before admitting children' % cls)


#: the child bootstrap: written at the top of a child host's sitecustomize.py, before any application import
BOOTSTRAP = r'''
import os, sys
_GUARD_STATE = os.environ.get('LAPLACE_STATE')
assert _GUARD_STATE and _GUARD_STATE.startswith('/tmp/'), 'a child host must run against an isolated LAPLACE_STATE'
sys.path.insert(0, os.environ['LAPLACE_GUARD_TESTS'])
import runtime_guard
runtime_guard.install()
runtime_guard.ARMED = True
'''
