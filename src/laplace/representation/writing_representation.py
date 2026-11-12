"""WRITING REPRESENTATION (core consolidation R2, 2026-10-19): the one Writing entry to Atlas representation.

Writing keeps request bodies in content-addressed custody (writing.bodies). The custody it REQUIRES is one
``atlas.store.BlobStore`` at an explicit local root, ``<repository>/contract/writing_bodies``: the same store,
format and handles as before, with no telemetry or live-state selection and no import of the legacy Fabric bridge
(Git leases, provider seat identity, runtime capsule adoption, watcher orchestration live in laplace.representation.atlas_bridge
and are not needed to read or write a body).

  BlobStore                 the Atlas type Writing depends on (atlas.* stays the public, engine-neutral namespace)
  body_store(root)          the repository's body store at its explicit root; never a default live store
  legacy_custody_body(handle)
                            the EXPLICIT legacy fallback for a body reference whose store is not this repository's:
                            the nonlocal Atlas custody read through laplace.representation.atlas_bridge, imported only here and
                            only when a caller reaches it. writing.bodies refuses this path under a finite read
                            budget before it is called (AR-R2-R2); unbudgeted legacy reads keep it unchanged.

This module and laplace.representation.atlas_bridge are the two reviewed Atlas import boundaries (tests/test_atlas_seal.py
ALLOWLIST). Nothing here duplicates a body or event journal, and no store format, hash or role changes.
"""
from __future__ import annotations

from pathlib import Path

from atlas.store import BlobStore  # noqa: F401  the one Atlas type Writing body custody depends on
from atlas.errors import BlobMissing as BodyMissing, BlobHashMismatch as BodyHashMismatch  # noqa: F401
from laplace.representation.writing_bodies import STORE

#: where a repository keeps Writing bodies, relative to its root: the public reference's `store` field, one decision
BODY_STORE = tuple(STORE.split("/"))


def body_store(root: Path | str) -> BlobStore:
    """The repository's own body store at its explicit root."""
    return BlobStore(Path(root).resolve().joinpath(*BODY_STORE))


def legacy_custody_body(handle: str) -> bytes:
    """The nonlocal legacy custody read (Atlas live fabric through atlas_bridge), explicit and lazily imported.

    Returns the body's text bytes exactly as the legacy path always did: a non-text body resolves to no text."""
    from laplace.representation import atlas_bridge
    body = atlas_bridge.custody_body(handle=str(handle))
    return (body.get("text") or "").encode("utf-8")
