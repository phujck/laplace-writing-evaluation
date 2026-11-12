"""The public repository perimeter: which repository paths may be cited as public evidence or pinned as reviewed input.

Refused lexically, before anything is stat'ed or hashed: absolute or traversing spellings, private/runtime namespaces,
secret names and suffixes, runtime locks, and any symlink component. Standard library only; no import-time effects.
"""
from __future__ import annotations

# THE PUBLIC REPOSITORY PERIMETER (repair1 WR-R1, repair2 WR-R1-R1, 2026-10-16): a repository path that may be cited as
# public evidence or pinned as a reviewed input. It is the declared superset of every namespace the evaluator export
# fences (scripts/writing_eval_manifest.py PRIVATE, CACHES, SECRET_NAMES and its suffix rules; tests cross-check the
# two) plus the runtime state homes and the disposable research preview staging (writing/research_artifact_read.py
# `.research_previews`); refused lexically, before anything is stat'ed or hashed. Authored data/results/evidence
# directories carry none of these names and stay usable.
PRIVATE_NAMESPACES = frozenset({'.git', '.ssh', '.codex', '.claude', 'soul', 'soul_dump', 'soul_corpus', 'soul_vectors',
                                'private', 'raw_calibration', 'provider_transcripts', '.provider-events',
                                '.laplace-state', '.laplace-cache'})
RUNTIME_NAMESPACES = frozenset({'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'node_modules', '.venv',
                                '.lake', '.research_previews'})
SECRET_NAMES = frozenset({'id_rsa', 'id_ed25519', 'credentials.json', 'auth.json', '.claude.json', '.mcp.json'})
SECRET_SUFFIXES = frozenset({'.pem', '.key'})
RUNTIME_SUFFIXES = frozenset({'.pyc'})
#: lock files are runtime coordination, except the two authored dependency locks
AUTHORED_LOCKS = frozenset({'uv.lock', 'poetry.lock'})


def _not_public(parts) -> bool:
    from pathlib import Path
    name = parts[-1] if parts else ''
    suffix = Path(name).suffix
    return bool('..' in parts or set(parts) & (PRIVATE_NAMESPACES | RUNTIME_NAMESPACES) or name in SECRET_NAMES
                or name == '.env' or name.startswith('.env.') or suffix in SECRET_SUFFIXES | RUNTIME_SUFFIXES
                or (suffix == '.lock' and name not in AUTHORED_LOCKS))


def public_repository_path(root, relative):
    """The exact public file ``relative`` names inside ``root``, or ValueError: absolute, traversal, backslash,
    private/runtime/secret namespace or a symlink component (inside or out) is refused before any read."""
    from pathlib import Path
    if not isinstance(relative, str) or not relative or relative.startswith('/') or '\\' in relative:
        raise ValueError('PRIVATE_OR_UNOWNED: a public evidence path is a repository-relative spelling: ' + str(relative))
    parts = Path(relative).parts
    if _not_public(parts):
        raise ValueError('PRIVATE_OR_UNOWNED: not a public repository path (private, runtime, cache or secret): ' + relative)
    root = Path(root).resolve()
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('PRIVATE_OR_UNOWNED: a symlinked path is not public evidence: ' + relative)
    if not path.resolve().is_relative_to(root):
        raise ValueError('PRIVATE_OR_UNOWNED: path escapes the repository: ' + relative)
    return path
