"""Owned-effect receipts: the exact, ephemeral record of what one owner wrote.

A file receipt names the repository-relative path and three byte identities (laplace.core.identity):
before the write, the bytes the owner intended, and the bytes observed after it; a bundle groups an
owner's file/object receipts, rewired records and the views they invalidate. Owners return bundles as
``owned_changes``; mutation attribution compares them with what is actually on disk.
"""
from __future__ import annotations

from pathlib import Path

from laplace.core.identity import bytes_digest

SCHEMA = "laplace.owner-mutation/1"


def file_receipt(root: Path, path: Path, before: bytes | None,
                 intended_after: bytes | None) -> dict:
    root, path = Path(root).resolve(), Path(path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("mutation receipt file escapes the active checkout")
    observed = path.read_bytes() if path.is_file() else None
    return {"scope":"repository","path":path.relative_to(root).as_posix(),
            "before_sha256":bytes_digest(before),"after_sha256":bytes_digest(intended_after),
            "observed_after_sha256":bytes_digest(observed)}


def bundle(*, files=(), objects=(), rewire_records=(), views=()) -> dict:
    return {"schema_version":SCHEMA,"files":list(files),"objects":list(objects),
            "rewire_records":list(rewire_records),"views":list(dict.fromkeys(views))}
