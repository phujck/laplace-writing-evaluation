"""Real workflow HTTP owner on a public synthetic root, with before-import containment.

Started by workflow_editor.playwright.mjs. The server binds loopback only and starts
no provider. Source belongs to this checkout; every mutable root belongs to the
explicit evidence home. Reuses the existing runtime_guard provider/live-state fence.
"""
import importlib.machinery
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
HOME = Path(os.environ['WORKFLOW_EVIDENCE_HOME']).resolve()
FIXTURE_PARENTS = (Path('/tmp/laplace-programme-20261024/workflow-consumer'),
                   Path('/tmp/laplace-programme-20261024/p3-integration'))
assert any(HOME.is_relative_to(parent) for parent in FIXTURE_PARENTS)
(HOME / 'tmp').mkdir(parents=True, exist_ok=True)
os.environ.update(TMPDIR=str(HOME / 'tmp'), TMP=str(HOME / 'tmp'), TEMP=str(HOME / 'tmp'))
assert not any(name == 'laplace' or name.startswith('laplace.') for name in sys.modules)
sys.path.insert(0, str(SOURCE / 'tests'))
import runtime_guard
runtime_guard.install()
runtime_guard.ARMED = True
refusals = []


class SelectedSource:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('laplace', 'atlas') or fullname.startswith(('laplace.', 'atlas.')):
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec and spec.origin and spec.origin not in ('built-in', 'frozen'):
                assert Path(spec.origin).resolve().is_relative_to(SOURCE / 'src'), (fullname, spec.origin)
            return spec


sys.meta_path.insert(0, SelectedSource())


def fixture_writes(event, args):
    targets = []
    if event == 'open' and args and not isinstance(args[0], int):
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)):
            targets.append((args[0], None))
    elif event in ('os.remove', 'os.rmdir'):
        targets.append((args[0], args[1]))
    elif event == 'os.mkdir':
        targets.append((args[0], args[2]))
    elif event == 'os.rename':
        targets.extend(((args[0], args[2]), (args[1], args[3])))
    for target, dir_fd in targets:
        if not isinstance(target, (str, bytes, os.PathLike)):
            continue
        resolved = Path(os.fsdecode(target))
        if not resolved.is_absolute() and isinstance(dir_fd, int) and dir_fd >= 0:
            resolved = Path(os.readlink('/proc/self/fd/%d' % dir_fd)) / resolved
        resolved = resolved.resolve()
        if not resolved.is_relative_to(HOME) and resolved != Path('/dev/null'):
            refusals.append({'event': event, 'path': str(resolved)})
            raise PermissionError('workflow fixture write outside evidence home: ' + str(resolved))


sys.addaudithook(fixture_writes)
from laplace.core import checkout
assert checkout.source_tree().resolve() == SOURCE
assert checkout.repo_root().resolve() == SOURCE
assert checkout.state_root().resolve() == HOME / 'state'
root = HOME / 'workspace'
root.mkdir(parents=True, exist_ok=True)
(root / 'node.py').write_text('VALUE = 1\n')
(root / 'registry_projects.json').write_text('{"projects": []}')
(root / 'profiles').mkdir(exist_ok=True)
cache = root / '.laplace-cache'
cache.mkdir(exist_ok=True)
(cache / 'writing-provider-catalogue.json').write_text(json.dumps({
    'schema_version': 'laplace.provider-catalogue/1', 'observed_at': 99999999999,
    'providers': [{'id': 'codex', 'available': True, 'models': []}, {'id': 'claude', 'available': True, 'models': []}]}))
os.environ.update(LAPLACE_REPO_ROOT=str(root), LAPLACE_ROOT=str(root),
                  LAPLACE_NO_PREWARM='1', LAPLACE_TEST_PROCESS='1',
                  LAPLACE_SESSION_WORKSPACES=str(HOME / 'session-workspaces'))
assert checkout.repo_root().resolve() == root
from laplace.web import scanner


def origins():
    loaded = {name: str(Path(module.__file__).resolve()) for name, module in sys.modules.items()
              if (name in ('laplace', 'atlas') or name.startswith(('laplace.', 'atlas.'))) and getattr(module, '__file__', None)}
    assert all(Path(path).is_relative_to(SOURCE / 'src') for path in loaded.values()), loaded
    return loaded


server = ThreadingHTTPServer(('127.0.0.1', 0), scanner.make_handler())
threading.Thread(target=server.serve_forever, daemon=True).start()
print(json.dumps({'port': server.server_address[1], 'root': str(root), 'source': str(SOURCE)}), flush=True)
try:
    sys.stdin.read()
finally:
    server.shutdown()
    server.server_close()
    (HOME / 'guard.json').write_text(json.dumps({'source': str(SOURCE), 'workspace': str(root),
        'state': str(checkout.state_root()), 'origins': origins(), 'refusals': refusals,
        'runtime_refusals': runtime_guard.DENIALS}, indent=2))
