"""Stdlib-only host selection shared by the engine and the OS-native entry.

Loaded directly by native_writing under -I: no Laplace import, service or write.
Code/runtime, data, receipt file, engine state and provider cwd are distinct facts.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys

SCHEMA = 'laplace.managed-homes/1'


def receipt_path(value=None):
    if value is not None:
        return Path(value)
    base = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local' / 'state'))
    return base / 'laplace' / 'writing-app.json'


def default_session_workspaces(workspace, state):
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'Laplace'
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support' / 'Laplace'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'laplace'
    key = os.path.normcase(str(workspace)) + '\0' + os.path.normcase(str(state))
    return base / 'session-workspaces' / hashlib.sha256(key.encode()).hexdigest()[:24]


def resolve(code_root, *, state=None, workspace_root=None, engine_state=None, session_workspaces=None):
    code = Path(code_root).resolve()
    separate = workspace_root is not None
    if not separate and (engine_state is not None or session_workspaces is not None):
        raise ValueError('Engine/session selection requires explicit --workspace-root')
    workspace = Path(workspace_root).expanduser().resolve() if separate else code
    receipt = receipt_path(state)
    engine = sessions = None
    if separate:
        if not (workspace / 'registry_projects.json').is_file() or not (workspace / 'profiles').is_dir():
            raise ValueError('Explicit workspace requires registry_projects.json and profiles/')
        if state is None:
            key = hashlib.sha256(str(workspace).encode()).hexdigest()[:24]
            receipt = receipt.parent / 'workspaces' / key / receipt.name
        receipt = receipt.expanduser().resolve()
        engine = Path(engine_state).expanduser().resolve() if engine_state is not None else workspace / '.laplace-state'
        sessions = (Path(session_workspaces).expanduser().resolve() if session_workspaces is not None
                    else default_session_workspaces(workspace, engine).resolve())
        if receipt in {workspace, engine, sessions} or engine == sessions or engine == workspace or sessions == workspace:
            raise ValueError('Receipt, workspace, engine state and session homes have distinct meanings')
        if receipt.exists() and not receipt.is_file():
            raise ValueError('Managed receipt must be a file')
        if any(path.exists() and not path.is_dir() for path in (engine, sessions)):
            raise ValueError('Engine/session home must be a directory')
    profile = receipt.parent / 'writing-native'
    if separate:
        profile = profile / hashlib.sha256((str(workspace) + '\0' + str(receipt)).encode()).hexdigest()[:24]
    return {'schema_version': SCHEMA, 'separate': separate, 'code_root': str(code),
            'workspace_root': str(workspace), 'receipt': str(receipt),
            'engine_state': str(engine) if engine else None, 'session_workspaces': str(sessions) if sessions else None,
            'native_profile': str(profile), 'association_root': str(workspace if separate else code)}


def workspace_snapshot(root):
    """Workspace-owned profiles are data/resource provenance, never executable source."""
    root = Path(root).resolve()
    rows = []
    for path in sorted((root / 'profiles').rglob('*')):
        if path.is_file():
            raw = path.read_bytes()
            rows.append({'path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
    identity = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'schema_version': 'laplace.workspace-resource-basis/1', 'root': str(root),
            'identity': identity, 'basis': 'workspace profiles/configuration', 'files': rows,
            'executable_source': False}


def viewer_identity(homes, host='127.0.0.1', port=8771):
    """One complete registration identity. Endpoint is not a storage-root selector."""
    if not homes['separate']:
        basis = str(Path(homes['code_root']).resolve()) + '\0' + str(Path(homes['receipt']).resolve())
    else:
        if host not in {'127.0.0.1', 'localhost', '::1'} or not 1 <= int(port) <= 65535:
            raise ValueError('Native viewer requires a loopback host and valid port')
        basis = '\0'.join([*(homes[key] for key in
            ('code_root', 'workspace_root', 'receipt', 'engine_state', 'session_workspaces')), host, str(int(port))])
    return 'org.laplace.Writing.p' + hashlib.sha256(basis.encode()).hexdigest()[:16]
