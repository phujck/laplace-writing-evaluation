"""ids.py - the one hashing law. Every derived identity in atlas is a hash of canonical JSON.

Canonical JSON here means exactly: ``sort_keys=True``, ``separators=(",", ":")``,
``ensure_ascii=False``, encoded UTF-8. Sorted keys make the hash independent of construction
order; tight separators make it independent of pretty-printing; ``ensure_ascii=False`` keeps
one byte sequence per string instead of two (escaped and unescaped) that hash differently.

No wall-clock and no randomness ever enters an id. Timestamps are recorded beside records and
excluded from the hashed field set (see ``schema.hashed_fields``), so re-deriving the same
content at a different second reproduces the same id. That property is a Phase 1 gate: an
instrument whose ids move under a clock cannot measure anything.

``scripts/export_atlas_snapshot.py`` on the laplace side re-implements these two functions
rather than importing them - the seal is one-way and carries no code. The agreement is checked
mechanically, not trusted: ``snapshot.verify`` recomputes the exporter's ``snapshot_id`` with
the functions here and refuses on disagreement.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .errors import NotCanonicalizable

# Every hash string in atlas carries its algorithm. A bare hex digest in a record is a future
# migration with no way to tell the generations apart.
HASH_PREFIX = "sha256:"


def canonical_json(obj: Any) -> str:
    """The one serialization used for hashing. Refuses anything json cannot encode."""
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise NotCanonicalizable(
            "value has no canonical JSON form", type=type(obj).__name__, error=str(exc)
        ) from exc


def chash(obj: Any) -> str:
    """Content hash of a value: sha256 over its canonical JSON, prefixed with the algorithm."""
    return HASH_PREFIX + hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def hash_bytes(data: bytes) -> str:
    """Content hash of raw bytes - the form used for source blobs, which are never re-encoded."""
    return HASH_PREFIX + hashlib.sha256(data).hexdigest()


def hex_of(hash_string: str) -> str:
    """The hex digest inside a prefixed hash string; refuses an unprefixed or foreign one."""
    if not hash_string.startswith(HASH_PREFIX):
        raise NotCanonicalizable("hash string is not sha256-prefixed", value=hash_string)
    return hash_string[len(HASH_PREFIX):]
