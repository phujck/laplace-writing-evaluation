"""RESEARCH READ OBSERVATION (S1 B5): the one context-local ledger of what a derivation consumed.

THE DERIVATION READ LEDGER (Sol RESEARCH-CACHE closure, 2026-10-12).

A state derivation reads far more than its index files: run receipts beside run jobs,
result outputs, producer declarations, the files it hashes, and existence probes. The
witness used to be a hand-maintained list of paths, and a path missing from the list
(`<run>.receipt.json`) let a cache hit publish a state the receipt had already changed.
Now every primitive that consumes a file during a derivation records the file's identity
AT THE MOMENT IT IS CONSUMED in a context-local ledger (`_observe`): `_read_object`, `_digest`
and the existence probe `_present`. The witness is the ledger plus the index files and scan
roots, and publication requires the post-derivation identities to equal the consumed ones
(writing.research_catalogue). tests/test_shared_reads_batch.py::test_research_derivation_footprint_is_fully_witnessed
traces every pathlib read and probe under the fixture root during a derivation and asserts
each is witnessed, so a new read path cannot silently fall outside the cache's eyes.

Live facts — process liveness and deadlines of RUNNING jobs — are not files. A derivation
that sampled them is retained only for STATE_CACHE_LIVE_TTL_S (writing.research_catalogue) and
says so in `read_basis.live_facts` (`_note_live`).

  _READ_LEDGER      the ONE ContextVar; research_catalogue._derive_state opens it per derivation.
  _stat_identity    (mtime_ns, ctime_ns, size, inode) of one path, or None.
  _observe / _present / _read_object / _digest / _relative_digest
                    consumption primitives: the value plus its identity, recorded at read time.
  _object_digest    canonical JSON digest.
  (a repository file's before/after receipt is laplace.core.receipts.file_receipt, the one definition)
"""
from __future__ import annotations

import contextvars
import hashlib
import json
from pathlib import Path
from typing import Any

from laplace.research import research_context


_READ_LEDGER: contextvars.ContextVar = contextvars.ContextVar('research_read_ledger', default=None)


def _stat_identity(path: Path):
    try:
        st = path.stat()
        return (st.st_mtime_ns, st.st_ctime_ns, st.st_size, st.st_ino)
    except OSError:
        return None


def _observe(path: Path) -> None:
    """Record `path`'s identity at consumption time in the active derivation ledger."""
    ledger = _READ_LEDGER.get()
    if ledger is not None:
        key = str(path)
        if key not in ledger['files']:
            ledger['files'][key] = _stat_identity(path)


def _present(path: Path) -> bool:
    """An existence probe that the derivation witness sees."""
    _observe(path)
    return path.is_file()


def _note_live(run_id: str, fact: dict) -> None:
    """A process/deadline observation: true only at the instant it was sampled."""
    ledger = _READ_LEDGER.get()
    if ledger is not None:
        ledger['live'][str(run_id)] = fact


def _read_object(path: Path, empty: dict, *, max_bytes: int | None = None) -> tuple[dict, str | None]:
    _observe(path)
    if not path.exists():
        return dict(empty), None
    try:
        if max_bytes is None:
            value = json.loads(path.read_text(encoding="utf-8"))
        else:
            with path.open('rb') as stream:
                raw = stream.read(max_bytes + 1)
            if len(raw) > max_bytes:
                return dict(empty), f"metadata exceeds bounded read: {path.name}"
            value = json.loads(raw)
    except (OSError, ValueError):
        return dict(empty), f"unreadable JSON: {path.name}"
    if not isinstance(value, dict):
        return dict(empty), f"JSON object required: {path.name}"
    return value, None


def _digest(path: Path) -> dict[str, Any]:
    """One exact dependency observation.  Only declared paths reach here."""
    _observe(path)
    try:
        data = path.read_bytes()
    except OSError:
        return {"path": path.name, "status": "MISSING"}
    return {"path": path.name, "status": "PRESENT", "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def _relative_digest(manuscript: Path, raw: str, *, _cache: dict | None = None) -> dict[str, Any]:
    path = research_context.inside(manuscript, raw)
    if path is None:
        return {"path": raw, "status": "REFUSED"}
    key=None
    if _cache is not None:
        try:
            stat=path.stat();key=(str(path),stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size)
        except OSError:key=(str(path),None,None,None)
    observation = dict(_cache[key]) if key is not None and key in _cache else _digest(path)
    if key is not None:_cache[key]=dict(observation)
    observation["path"] = path.relative_to(manuscript).as_posix()
    return observation


def _object_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False).encode("utf-8")).hexdigest()


