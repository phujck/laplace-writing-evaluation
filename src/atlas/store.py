"""store.py - a thin causal ledger, compressed content hives and disposable indexes.

The canonical event chain is the small ``conceptric.sqlite3`` ledger.  Exact event envelopes live
in a compressed content-addressed hive; the ledger records their handles and the hive layout is
derived from those handles.  Resolvable objects and typed edges live in a separate disposable
``conceptric.index.sqlite3`` projection.  A fresh process reconstructs that projection from the
ledger plus verified hive bytes, so losing an index never loses authored content.

Schema-v1 stores remain readable and writable without an implicit migration.  ``migrate_hived``
is the explicit, locked transition to schema v2; this is important for the live seat fabric, whose
only transport is ``ConceptricStore.append``.  New stores are hived from birth.

Blob layout is ``blobs/<hex[:2]>/<hex>`` - two levels so a twelve-thousand-node snapshot does
not put twelve thousand entries in one directory. The key stored in a record is the prefixed
hash string (``sha256:...``); the path is derived from it, never stored, so a re-layout does not
invalidate a manifest.

Reads verify. ``BlobStore.get`` re-hashes what it read and refuses on disagreement rather than
returning bytes that no longer match the key they were filed under.
"""

from __future__ import annotations

import errno
import json
import os
import platform
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
import zlib
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .errors import (
    AtlasError,
    BlobHashMismatch,
    BlobMissing,
    HistoryChainMismatch,
    StateTransitionRefused,
    StaleOwner,
    StoreError,
    StoreLockTimeout,
)
from .history import (
    AtlasEvent,
    AuthorityCheckpoint,
    ConceptricObject,
    EventKind,
    MessageMigrationSupersession,
    SeatJoinReceipt,
    SeatMessage,
    SeatOccupancyBinding,
    SeatTransition,
)
from .ids import HASH_PREFIX, canonical_json, chash, hash_bytes, hex_of
from .state import (
    ConceptricState,
    SeatOccupancy,
    apply_event,
    authority_checkpoint_projection,
    effective_region_lease_projection,
)

_AUTHORITY_CONTEXT_REPOSITORY = Path(__file__).resolve().parents[2]
_AUTHORITY_CONTEXT_RELATIVE_PATHS = (
    "src/atlas/errors.py",
    "src/atlas/history.py",
    "src/atlas/ids.py",
    "src/atlas/state.py",
    "src/atlas/store.py",
)
def _authority_path(relative: str | Path) -> Path:
    relative=Path(relative)
    source=(_AUTHORITY_CONTEXT_REPOSITORY/relative).resolve()
    if source.is_file():return source
    parts=relative.parts
    if parts[:2]==("src","atlas"):
        installed=(Path(__file__).resolve().parent/Path(*parts[2:])).resolve()
        if installed.is_file():return installed
    return source
# Captured when this Python generation loads.  A later disk edit cannot make an old process
# claim the new source merely by re-hashing the filesystem at append time.
_LOADED_AUTHORITY_FILE_DIGESTS = {
    relative: hash_bytes(_authority_path(relative).read_bytes())
    for relative in _AUTHORITY_CONTEXT_RELATIVE_PATHS
}

# Caller files are pinned at first declaration in this Python generation. Only the
# explicitly supplied tuple participates in each context; declarations do not widen others.
_LOADED_EXTRA_AUTHORITY_FILE_DIGESTS: dict[Path, str] = {}

PORTABLE_AUTHORITY_ADOPTION_SCHEMA = "atlas.portable-authority-adoption/2"
PORTABLE_AUTHORITY_ADOPTION_META_KEY = "portable_authority_adoption_json"


def _atomic_temp(path: Path) -> tuple[Path, int]:
    """Create one private sibling temp so concurrent writers cannot steal each other's file."""

    fd, raw = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp = Path(raw)
    try:
        mode = (path.stat().st_mode & 0o777) if path.exists() else 0o644
        os.fchmod(fd, mode)
    except OSError:
        os.close(fd)
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return tmp, fd


def _fsync_directory(path: Path) -> None:
    """Make a completed rename durable in its containing directory."""

    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise StoreError("store directory fsync failed", path=str(path)) from exc


def write_atomic(path: Path, data: bytes) -> None:
    """Write bytes to ``path`` atomically: temp file in the same directory, fsync, replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    try:
        tmp, fd = _atomic_temp(path)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise StoreError("atomic write failed", path=str(path), error=str(exc)) from exc
    finally:
        # Unique temps make this cleanup private to this writer.  With the old fixed ``.tmp``
        # name, one writer could unlink another writer's pending source after losing the race.
        if tmp is not None:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


def jsonl_bytes(records: Iterable[dict[str, Any]]) -> bytes:
    """Serialize records to jsonl using the canonical encoding, so the file itself hashes."""
    out = []
    for rec in records:
        out.append(canonical_json(rec))
        out.append("\n")
    return "".join(out).encode("utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    """Write a whole jsonl file atomically, streaming. Returns the row count.

    Streamed rather than serialized in one piece: a repo-scale span file is hundreds of
    thousands of rows, and holding them plus their JSON at once costs more than the write.
    Atomicity is unchanged - rows land in a sibling temp file that is fsynced and renamed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    count = 0
    try:
        tmp, fd = _atomic_temp(path)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            for record in records:
                fh.write(canonical_json(record))
                fh.write("\n")
                count += 1
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        raise StoreError("jsonl write failed", path=str(path), error=str(exc)) from exc
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
    return count


def append_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    """Append rows to a jsonl file. The append-only path: existing rows are never rewritten.

    Used by the growing stores (history, fitness). Bundle files use ``write_jsonl`` instead
    because a bundle is minted once and is immutable afterwards.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(records)
    try:
        with open(path, "ab") as fh:
            fh.write(jsonl_bytes(rows))
            fh.flush()
            os.fsync(fh.fileno())
    except OSError as exc:
        raise StoreError("jsonl append failed", path=str(path), error=str(exc)) from exc
    return len(rows)


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Stream a jsonl file. A malformed line is a named refusal, never a skipped row."""
    path = Path(path)
    try:
        fh = open(path, "r", encoding="utf-8")
    except OSError as exc:
        raise StoreError("jsonl file unreadable", path=str(path), error=str(exc)) from exc
    with fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError as exc:
                raise StoreError(
                    "jsonl row is not valid JSON", path=str(path), line=lineno, error=str(exc)
                ) from exc


def sha256_file(path: Path) -> str:
    """Prefixed sha256 of a file's bytes, read in chunks so a 19 MB store costs no more RAM."""
    import hashlib

    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError as exc:
        raise StoreError("file unreadable for hashing", path=str(path), error=str(exc)) from exc
    return HASH_PREFIX + h.hexdigest()


def _extra_authority_file_digests(paths: tuple[Path, ...]) -> dict[str, str]:
    """Pin caller-declared bytes on first use and refuse drift in this generation."""

    files = {}
    for declared in paths:
        path = (_AUTHORITY_CONTEXT_REPOSITORY / declared).resolve()
        digest = sha256_file(path)
        loaded = _LOADED_EXTRA_AUTHORITY_FILE_DIGESTS.setdefault(path, digest)
        if digest != loaded:
            raise StoreError(
                "authority context is UNKNOWN because loaded code differs from disk",
                path=str(path), loaded=loaded, disk=digest,
            )
        files[os.path.relpath(path, _AUTHORITY_CONTEXT_REPOSITORY)] = digest
    return files


class BlobStore:
    """Content-addressed bytes under ``root``. The key IS the hash; writing twice is a no-op."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def key_path(self, key: str) -> Path:
        hexd = hex_of(key)
        return self.root / hexd[:2] / hexd

    def has(self, key: str) -> bool:
        return self.key_path(key).is_file()

    def put(self, data: bytes) -> str:
        """Store bytes, return their key. Already-present blobs are not rewritten."""
        key = hash_bytes(data)
        path = self.key_path(key)
        if path.is_file():
            # The caller already hashed these bytes. Compare bounded chunks instead
            # of allocating/hashing a second whole blob, and never cache this check:
            # corruption between two puts must be observed by the second put.
            expected = memoryview(data)
            offset = 0
            try:
                with path.open("rb") as stream:
                    while chunk := stream.read(64 * 1024):
                        if chunk != expected[offset:offset + len(chunk)]:
                            raise BlobHashMismatch("blob bytes do not match their key", key=key)
                        offset += len(chunk)
            except OSError as exc:
                raise BlobMissing("blob unreadable", key=key, error=str(exc)) from exc
            if offset != len(data):
                raise BlobHashMismatch("blob bytes do not match their key", key=key)
        else:
            write_atomic(path, data)
        return key

    def get(self, key: str, *, max_bytes: int | None = None) -> bytes:
        """Read a blob and re-verify it against its key. Both failures are named refusals. With ``max_bytes`` (the
        size its reference declares) a larger blob is refused without being read whole."""
        path = self.key_path(key)
        if not path.is_file():
            raise BlobMissing("blob is not in the store", key=key, path=str(path))
        try:
            if max_bytes is None:
                data = path.read_bytes()
            else:
                with path.open("rb") as stream:
                    data = stream.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise BlobHashMismatch("blob is larger than its reference declares", key=key, limit=max_bytes)
        except OSError as exc:
            raise BlobMissing("blob unreadable", key=key, error=str(exc)) from exc
        actual = hash_bytes(data)
        if actual != key:
            raise BlobHashMismatch("blob bytes do not match their key", key=key, actual=actual)
        return data


class CompressedHive:
    """Verified compressed CAS whose identity is the *uncompressed* canonical content.

    Compression is storage morphology, never identity: changing a codec or packing chunks later
    does not move a handle.  The first layout is deliberately simple and independently readable:
    ``<root>/<sha256[:2]>/<sha256>.zlib``.
    """

    codec = "zlib/1"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def key_path(self, key: str) -> Path:
        hexd = hex_of(key)
        return self.root / hexd[:2] / f"{hexd}.zlib"

    def has(self, key: str) -> bool:
        return self.key_path(key).is_file()

    def put(self, data: bytes) -> str:
        key = hash_bytes(data)
        path = self.key_path(key)
        if path.is_file():
            # A colliding or poisoned incumbent must not be blessed by a no-op write.
            self.get(key)
            return key
        write_atomic(path, zlib.compress(data, level=9))
        return key

    def get(self, key: str) -> bytes:
        path = self.key_path(key)
        if not path.is_file():
            raise BlobMissing("hive chunk is not in the store", key=key, path=str(path))
        try:
            encoded = path.read_bytes()
            data = zlib.decompress(encoded)
        except (OSError, zlib.error) as exc:
            raise BlobHashMismatch(
                "hive chunk is unreadable or truncated", key=key, path=str(path)
            ) from exc
        actual = hash_bytes(data)
        if actual != key:
            raise BlobHashMismatch("hive content does not match its key", key=key, actual=actual)
        return data


HISTORY_ROW_SCHEMA = "atlas-history-row/1"
GENESIS_DIGEST = HASH_PREFIX + ("0" * 64)


@dataclass(frozen=True)
class StoredEvent:
    """One verified position in the chained conceptric history."""

    sequence: int
    previous_digest: str
    record_digest: str
    event: AtlasEvent

    def hashed_dict(self) -> dict[str, Any]:
        return {
            "schema_version": HISTORY_ROW_SCHEMA,
            "sequence": self.sequence,
            "previous_digest": self.previous_digest,
            "event": self.event.to_dict(),
        }

    def computed_digest(self) -> str:
        return chash(self.hashed_dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self.hashed_dict(), "record_digest": self.record_digest}

    @classmethod
    def create(cls, sequence: int, previous_digest: str, event: AtlasEvent) -> "StoredEvent":
        draft = cls(sequence, previous_digest, "", event)
        return cls(sequence, previous_digest, draft.computed_digest(), event)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StoredEvent":
        expected = {
            "schema_version",
            "sequence",
            "previous_digest",
            "record_digest",
            "event",
        }
        if set(raw) != expected or raw.get("schema_version") != HISTORY_ROW_SCHEMA:
            raise HistoryChainMismatch("history row shape or schema is unknown")
        try:
            stored = cls(
                sequence=raw["sequence"],
                previous_digest=raw["previous_digest"],
                record_digest=raw["record_digest"],
                event=AtlasEvent.from_dict(raw["event"]),
            )
        except (AtlasError, KeyError, TypeError, ValueError) as exc:
            raise HistoryChainMismatch("history row payload is malformed") from exc
        if stored.record_digest != stored.computed_digest():
            raise HistoryChainMismatch(
                "history row digest does not verify", sequence=stored.sequence
            )
        return stored


LEGACY_CONCEPTRIC_DB_SCHEMA = "atlas-conceptric-sqlite/1"
CONCEPTRIC_DB_SCHEMA = "atlas-conceptric-sqlite/2"
LEGACY_GRAPH_PROJECTION_SCHEMA = "atlas.conceptric-graph-projection/3"
GRAPH_PROJECTION_SCHEMA = "atlas.conceptric-graph-projection/6"
DEVELOPMENT_REVIEW_PROJECTION_SCHEMA = "atlas.development-review-projection/6"
DEVELOPMENT_REVIEW_FRONTIER_SCHEMA = "atlas.development-review-frontier/6"
SEAT_MAIL_PROJECTION_SCHEMA = "atlas.seat-mail-projection/2"
SEAT_MAIL_FRONTIER_SCHEMA = "atlas.seat-mail-frontier/2"
PROVIDER_SEAT_BINDING_FRONTIER_SCHEMA = "atlas.provider-seat-binding-frontier/2"
AUTHORITY_CHECKPOINT_SCHEMA = AuthorityCheckpoint.SCHEMA_VERSION
AUTHORITY_SUFFIX_LIMIT = 64
# Re-inflating a large hived tip dominates repeated authority reads.  The cached value is
# still checked against every compact ledger field (including its CAS handle) before reuse.
# The causal coordinate is store-independent: equal (cursor, head) names equal stored bytes.
_AUTHORITY_TIP_CACHE_LIMIT = 128
_AUTHORITY_TIP_CACHE_LOCK = threading.RLock()
_AUTHORITY_TIP_CACHE: dict[
    tuple[int, str], tuple[str, StoredEvent, Path, tuple[int, int]]
] = {}
AUTHORITY_AFFECTING_EVENT_KINDS = frozenset(
    {
        EventKind.LIFECYCLE.value,
        EventKind.SEAT.value,
        EventKind.SEAT_JOIN.value,
        EventKind.SEAT_OCCUPANCY_BINDING.value,
        EventKind.REGION_CHECKOUT.value,
        EventKind.REGION_CHECKIN.value,
        EventKind.REGION_PUBLICATION_PREPARED.value,
        EventKind.REGION_PUBLICATION_SIGNED.value,
        EventKind.REGION_PUBLICATION_AUTHORIZED.value,
        EventKind.REGION_PUBLICATION_FINALIZED.value,
        EventKind.ASSUMPTION.value,
        EventKind.TRANSPORT.value,
        EventKind.CORPUS_ACT.value,
        EventKind.REPL.value,
        EventKind.MESSAGE.value,
        EventKind.MESSAGE_PULL.value,
        EventKind.MESSAGE_ACK.value,
        EventKind.MESSAGE_PRESERVE_FORK.value,
        EventKind.MESSAGE_SUPERSESSION.value,
        EventKind.MESSAGE_MIGRATION_SUPERSESSION.value,
        EventKind.MESSAGE_EXPIRY.value,
    }
)
AUTHORITY_PROVEN_NEUTRAL_EVENT_KINDS = frozenset(
    {
        EventKind.GRADE_AXIS.value,
        EventKind.MOVE.value,
        EventKind.JOIN.value,
        EventKind.MATERIALIZATION.value,
        EventKind.PROJECTION.value,
        EventKind.DECISION.value,
        EventKind.PROMOTION.value,
        EventKind.PROLONGATION.value,
        EventKind.ROLLBACK.value,
        EventKind.OBSERVATION.value,
        EventKind.REVISION.value,
        EventKind.PERMISSION_REQUEST.value,
        EventKind.PERMISSION_DECISION.value,
        EventKind.OBJECT.value,
        EventKind.EDGE.value,
        EventKind.WATCHER.value,
        EventKind.WATCH_CHECKPOINT.value,
    }
)
LEGACY_UNTYPED_REVIEW_DECISIONS = {
    "message:13b859bdec653046358bd1a005ebbf7ff4d822d7490a2cf8005462d288330ae3": "REJECT",
    "message:fe619624ed76042612b2497c1f96e8725b74bc75354f422ea6e382805ed0c174": "ACCEPT",
    "message:2833c11c24fe7165116e36c6f64d02cf39a2770837408a1690aafdecd6e490f7": "CONTEST",
}
LEGACY_UNTYPED_REVIEW_VERDICT_IDS = frozenset(LEGACY_UNTYPED_REVIEW_DECISIONS)
DEFAULT_EVENT_HIVE_REF = "hives/events"
HIVE_MIGRATION_RECEIPT_SCHEMA = "atlas.hived-storage-migration-receipt/1"
HIVE_CUSTODY_RECEIPT_SCHEMA = "atlas.hive-custody-receipt/1"


#: THE DENIAL LIVES AT THE APPEND CAPABILITY, not at a helper above it.
#: The first cure guarded a host-side store factory and called it a write door.
#: Codex planted it and it was not: a direct ConceptricStore(root).append() bypassed the
#: helper entirely, and the guard compared against a COMPILED DEFAULT root, so
#:     LAPLACE_TEST_PROCESS=1 LAPLACE_STATE=/tmp/laplace-production-alt  ->  ALLOWED
#: because the configured live root was not the constant being guarded.
#:
#: So it inverts. Under a test process the rule is an ALLOWLIST, not a denylist: a write
#: is permitted only to a root a test could plausibly own — a pytest tmp dir, a path the
#: harness declared, or one carrying an explicit marker file. Every other root refuses,
#: including roots nobody thought to name. A denylist has to predict the production path;
#: an allowlist only has to recognise a test one.
_TEST_ROOT_MARKER = ".atlas-test-root"


class LiveStoreUnderTest(RuntimeError):
    """A test process tried to append to a store it does not own."""


def _refuse_test_write(root: Path) -> None:
    import os

    if not ("PYTEST_CURRENT_TEST" in os.environ or os.environ.get("LAPLACE_TEST_PROCESS") == "1"):
        return
    try:
        resolved = Path(root).resolve()
    except OSError:
        resolved = Path(root)
    # THE BARE /tmp IS NOT A TEST ROOT. My first allowlist matched any name starting
    # "tmp", so /tmp itself matched and EVERYTHING under it was admitted — codex's plant
    # at /tmp/laplace-production-alt sailed through a rule written to stop exactly it.
    # An allowlist that admits the world is a denylist wearing the other word.
    # pytest's own dirs are pytest-of-<user>/pytest-N/...; tempfile.mkdtemp gives
    # tmp + at least six random chars. Neither is the literal "tmp".
    import re as _re

    _MKDTEMP = _re.compile(r"^tmp[A-Za-z0-9_]{6,}$")
    parts = [p.name for p in (resolved, *resolved.parents)]
    # ".pytest-tmp" is the basetemp pyproject sets so no run writes to /tmp (2026-09-14): the guard
    # recognises a test root by NAME, so moving the basetemp must teach it the new name too.
    if any(n.startswith("pytest-") or n == ".pytest-tmp" or _MKDTEMP.match(n) for n in parts):
        return
    declared = os.environ.get("LAPLACE_TEST_STORE_ROOT")
    if declared and resolved == Path(declared).expanduser().resolve():
        return
    for cand in (resolved, *list(resolved.parents)[:3]):
        if (cand / _TEST_ROOT_MARKER).exists():
            return
    raise LiveStoreUnderTest(
        f"a test process tried to append to {resolved} — refused at the append "
        f"capability. A test may write to a pytest tmp root, to the root named by "
        f"LAPLACE_TEST_STORE_ROOT, or to one carrying a {_TEST_ROOT_MARKER} file. "
        f"If this fires in your test, the root was resolved after a monkeypatch was "
        f"torn down (typically from a daemon thread)."
    )


class ConceptricStore:
    """The one event write door over compact authority and reconstructible projections."""

    def __init__(
        self,
        root: Path,
        *,
        hive_root: Path | None = None,
        read_only: bool = False,
        immutable: bool = False,
        expected_store_role: str | None = None,
        authority_context: Mapping[str, str] | None = None,
        extra_authority_files: tuple[Path, ...] = (),
    ) -> None:
        self._extra_authority_files = tuple(
            (_AUTHORITY_CONTEXT_REPOSITORY / path).resolve()
            for path in extra_authority_files
        )
        _extra_authority_file_digests(self._extra_authority_files)
        self.root = Path(root)
        self.path = self.root / "conceptric.sqlite3"
        self.projection_path = self.root / "conceptric.index.sqlite3"
        self.legacy_path = self.root / "events.jsonl"
        self.legacy_receipt_path = self.root / "events.legacy-imported.jsonl"
        self.migration_receipt_path = self.root / "hive-migration-receipt.json"
        self.custody_receipt_path = self.root / "hive-custody-receipt.json"
        self.external_custody_receipt_path = self.root / "RECEIPT.json"
        self.lock_path = self.root / "conceptric.lock"
        self._requested_hive_root = None if hive_root is None else Path(hive_root)
        # This role comes from the production caller, outside the directory being admitted.
        # It distinguishes blueprint from runtime custody; it is deliberately not claimed as
        # a unique-authority witness, so a same-role whole-store clone remains an external-
        # custody problem rather than a tautological co-resident proof.
        self._expected_store_role = (
            None if expected_store_role is None else expected_store_role.strip()
        )
        if self._expected_store_role is not None:
            role_tokens = set(self._expected_store_role.casefold().replace("_", "-").split("-"))
            if not self._expected_store_role or role_tokens.intersection({"prod", "production"}):
                raise StoreError(
                    "expected custody role must be concrete and non-production",
                    store_role=self._expected_store_role,
                )
        self.read_only = bool(read_only)
        self.immutable = bool(immutable)
        if self.immutable and not self.read_only:
            raise StoreError("immutable SQLite access requires a read-only store")
        self.hive_root = self.root / DEFAULT_EVENT_HIVE_REF
        self.hive = CompressedHive(self.hive_root)
        self.schema_version = CONCEPTRIC_DB_SCHEMA
        # The append cache is a verified fold, never a second authority. Construction or an
        # observed external tip change rebuilds it from the exact history; ordinary appends
        # then fold only their packet onto this head instead of inflating the entire hive.
        self._verified_cache_lock = threading.RLock()
        self._verified_state = ConceptricState()
        self._verified_sequence = 0
        self._verified_head_digest = GENESIS_DIGEST
        self._authority_context = self._normalize_authority_context(
            authority_context,
            root=self.root,
            store_role=self._expected_store_role,
            extra_authority_files=self._extra_authority_files,
        )
        if self.read_only:
            with self._locked(shared=True):
                self._open_existing_database()
        else:
            with self._locked():
                self._refuse_genesis_over_custody()
                self._ensure_database()

    def _refuse_genesis_over_custody(self) -> None:
        """Never found an empty ledger beside evidence that an authority already existed.

        SQLite creates a database merely by opening a missing path.  That is appropriate for an
        explicitly new store, but catastrophic after a partial clone, an LFS miss, or accidental
        ledger deletion: migration/seal receipts and hive chunks are custody evidence, not an
        invitation to mint a clean-looking genesis beside them.
        """

        # Provider extensions (message blobs today, other hives later) must not be taught to
        # this class one filename at a time.  Every persistent sibling says this root has a
        # history.  The lock is the sole exception because entering this method created it.
        evidence: list[str] = []
        try:
            evidence.extend(
                str(path)
                for path in sorted(self.root.iterdir(), key=lambda item: item.name)
                if path.name not in {self.path.name, self.lock_path.name}
            )
        except OSError as exc:
            raise StoreError(
                "custody root could not be inspected before genesis",
                path=str(self.root),
                error=str(exc),
            ) from exc
        candidate_hives = {
            self._requested_hive_root,
        }
        for hive_root in sorted(
            (Path(path) for path in candidate_hives if path is not None),
            key=str,
        ):
            try:
                witness = next((path for path in hive_root.rglob("*") if path.is_file()), None)
            except OSError as exc:
                raise StoreError(
                    "custody evidence could not be inspected before genesis",
                    path=str(hive_root),
                    error=str(exc),
                ) from exc
            if witness is not None:
                evidence.append(str(witness))
        if not evidence:
            return

        ledger_schema: str | None = None
        ledger_error: str | None = None
        ledger_has_identity = False
        ledger_has_portable_adoption = False
        if self.path.is_file():
            try:
                with self._open_sqlite(self.path, read_only=True) as connection:
                    ledger_schema = self._schema_version(connection)
                    if ledger_schema == CONCEPTRIC_DB_SCHEMA:
                        ledger_has_identity = (
                            connection.execute(
                                "SELECT 1 FROM meta WHERE key = 'store_identity_json'"
                            ).fetchone()
                            is not None
                        )
                        ledger_has_portable_adoption = (
                            connection.execute(
                                "SELECT 1 FROM meta WHERE key = ?",
                                (PORTABLE_AUTHORITY_ADOPTION_META_KEY,),
                            ).fetchone()
                            is not None
                        )
            except (StoreError, sqlite3.DatabaseError) as exc:
                ledger_error = str(exc)
        if ledger_schema in (LEGACY_CONCEPTRIC_DB_SCHEMA, CONCEPTRIC_DB_SCHEMA):
            travelling_v2 = False
            if self.external_custody_receipt_path.is_file():
                try:
                    travelling = json.loads(
                        self.external_custody_receipt_path.read_text(encoding="utf-8")
                    )
                    travelling_v2 = (
                        travelling.get("schema_version") == "laplace.runtime-atlas-custody/2"
                    )
                except (OSError, ValueError):
                    travelling_v2 = True
            if travelling_v2 and not ledger_has_portable_adoption:
                ledger_error = (
                    "travelling custody capsule v2 is read-only until an external grant and "
                    "explicit portable checkpoint adoption are committed"
                )
            elif self.custody_receipt_path.is_file():
                try:
                    self._verify_sealed_prefix_admission()
                except (StoreError, sqlite3.DatabaseError, OSError, ValueError) as exc:
                    ledger_error = str(exc)
                else:
                    return
            elif self.external_custody_receipt_path.exists():
                ledger_error = (
                    "travelling custody snapshot requires read-only verification and an "
                    "explicit restore act before writable admission"
                )
            elif ledger_has_identity:
                ledger_error = (
                    "sealed ledger identity survives but its custody receipt is missing; "
                    "deleting the co-resident proof cannot reopen writable authority"
                )
            else:
                return
        raise StoreError(
            "conceptric genesis refused beside existing custody evidence",
            ledger=str(self.path),
            ledger_state=(
                "missing"
                if not self.path.exists()
                else "not-file"
                if not self.path.is_file()
                else "empty"
                if self.path.stat().st_size == 0
                else "unknown-schema"
            ),
            ledger_schema=ledger_schema,
            ledger_error=ledger_error,
            evidence=tuple(evidence),
            action="restore the authoritative ledger; never found over receipts or hives",
        )

    def _verify_sealed_prefix_admission(self) -> None:
        """Bind a writable open to the exact authority named by its custody evidence.

        A custody seal is a commit boundary, not a ban on later appends.  Admission therefore
        proves that the sealed head is an exact prefix of the ledger being opened and that both
        faces name the same store role.  A schema string alone proves neither: an empty database
        created by this class and an unrelated Atlas ledger both carry perfectly valid schemas.

        The full custody verifier remains the commit-shaped, zero-orphan proof.  This bounded
        check exists earlier in construction so a poisoned ledger cannot be accepted and then
        use projection repair to erase the evidence that exposed the substitution.
        """

        receipt = self._read_receipt(self.custody_receipt_path, schema=HIVE_CUSTODY_RECEIPT_SCHEMA)
        with self._open_sqlite(self.path, read_only=True) as connection:
            schema = self._schema_version(connection)
            if schema != CONCEPTRIC_DB_SCHEMA:
                raise StoreError(
                    "custody evidence requires a hived schema-v2 ledger",
                    expected=CONCEPTRIC_DB_SCHEMA,
                    got=schema,
                )
            meta = self._meta_values(connection)
            current_count, _current_head = self._compact_tip(connection)

            sealed_count = receipt.get("event_count")
            if type(sealed_count) is not int or sealed_count < 0:
                raise StoreError(
                    "custody evidence has an invalid sealed event count",
                    event_count=sealed_count,
                )
            if sealed_count > current_count:
                raise StoreError(
                    "ledger is shorter than the sealed custody prefix",
                    sealed_event_count=sealed_count,
                    ledger_event_count=current_count,
                )
            if sealed_count == 0:
                raise StoreError(
                    "custody admission refuses a zero-event seal",
                    sealed_event_count=sealed_count,
                )
            prefix = connection.execute(
                "SELECT record_digest FROM events WHERE sequence = ?",
                (sealed_count,),
            ).fetchone()
            if prefix is None:
                raise StoreError(
                    "sealed custody prefix is absent from the ledger",
                    sealed_event_count=sealed_count,
                )
            prefix_head = str(prefix["record_digest"])

        sealed_head = receipt.get("head_digest")
        if sealed_head != prefix_head:
            raise StoreError(
                "ledger content disagrees with the sealed custody prefix",
                sealed_event_count=sealed_count,
                expected_head=sealed_head,
                got_head=prefix_head,
            )
        if receipt.get("ledger_ref") != self.path.name:
            raise StoreError(
                "custody evidence names a different ledger",
                expected=self.path.name,
                got=receipt.get("ledger_ref"),
            )
        receipt_identity = self._validate_store_identity(
            receipt.get("store_identity"), operation="custody admission"
        )
        try:
            ledger_identity = json.loads(meta["store_identity_json"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StoreError("ledger has no readable sealed store identity") from exc
        ledger_identity = self._validate_store_identity(
            ledger_identity, operation="ledger admission"
        )
        if ledger_identity != receipt_identity:
            raise StoreError(
                "ledger identity disagrees with custody evidence",
                ledger_identity=ledger_identity,
                receipt_identity=receipt_identity,
            )

    @contextmanager
    def _locked(self, *, shared: bool = False, timeout: float = 30.0) -> Iterator[None]:
        """Take the cross-process store lock with a finite wait.

        Lock acquisition/release faults are store faults.  An ``OSError`` raised
        *by the protected body* is not: it propagates with its real identity so a
        disk-full/permission failure cannot be mislabeled ``database lock failed``.
        """
        import fcntl

        if not self.read_only:
            self.root.mkdir(parents=True, exist_ok=True)
        elif not self.root.is_dir():
            raise StoreError("read-only conceptric root does not exist", path=str(self.root))
        # A read-only face never creates even a derived coordination file. If a
        # fresh clone has no lock yet, the persistent appearance of one during
        # the body proves a writer raced the unlocked snapshot and the read is
        # refused below rather than returned as coherent.
        unlocked_read = self.read_only and not self.lock_path.is_file()
        if unlocked_read:
            yield
            if self.lock_path.exists():
                raise StoreError(
                    "writer appeared during an initially lock-free read-only snapshot",
                    path=str(self.lock_path),
                )
            return
        try:
            lock_mode = "rb" if self.read_only else "a+b"
            lock = open(self.lock_path, lock_mode)
        except OSError as exc:
            raise StoreError(
                "conceptric database lock could not be opened",
                path=str(self.lock_path),
                error=str(exc),
            ) from exc
        with lock:
            mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
            deadline = time.monotonic() + max(0.0, float(timeout))
            while True:
                try:
                    fcntl.flock(lock.fileno(), mode | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise StoreError(
                            "conceptric database lock acquisition failed",
                            path=str(self.lock_path),
                            error=str(exc),
                        ) from exc
                    if time.monotonic() >= deadline:
                        raise StoreLockTimeout(
                            "conceptric database lock timed out",
                            path=str(self.lock_path),
                            shared=shared,
                            timeout=float(timeout),
                        ) from exc
                    time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
            try:
                yield
            finally:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                except OSError as exc:
                    raise StoreError(
                        "conceptric database lock release failed",
                        path=str(self.lock_path),
                        error=str(exc),
                    ) from exc

    @staticmethod
    def _open_sqlite(
        path: Path, *, wal: bool = True, read_only: bool = False, immutable: bool = False
    ) -> sqlite3.Connection:
        try:
            if immutable and not read_only:
                raise StoreError("immutable SQLite access requires read-only mode")
            if read_only:
                query = "?mode=ro&immutable=1" if immutable else "?mode=ro"
                connection = sqlite3.connect(
                    path.resolve().as_uri() + query, uri=True, timeout=30.0
                )
            else:
                connection = sqlite3.connect(path, timeout=30.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            if read_only:
                connection.execute("PRAGMA query_only = ON")
            else:
                connection.execute(f"PRAGMA journal_mode = {'WAL' if wal else 'DELETE'}")
                connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA busy_timeout = 30000")
            return connection
        except sqlite3.Error as exc:
            raise StoreError(
                "conceptric database could not be opened", path=str(path), error=str(exc)
            ) from exc

    def _connect(self) -> sqlite3.Connection:
        return self._open_sqlite(self.path, read_only=self.read_only, immutable=self.immutable)

    def _connect_projection(self) -> sqlite3.Connection:
        return self._open_sqlite(
            self.projection_path, read_only=self.read_only, immutable=self.immutable
        )

    def _open_existing_database(self) -> None:
        """Bind an existing authority without creating, repairing or migrating it."""
        if not self.path.is_file():
            raise StoreError("read-only conceptric database does not exist", path=str(self.path))
        with self._connect() as connection:
            schema = self._schema_version(connection)
            if schema not in (LEGACY_CONCEPTRIC_DB_SCHEMA, CONCEPTRIC_DB_SCHEMA):
                raise StoreError(
                    "conceptric database schema is unknown",
                    expected=[LEGACY_CONCEPTRIC_DB_SCHEMA, CONCEPTRIC_DB_SCHEMA],
                    got=schema,
                )
            self.schema_version = schema
            if schema == CONCEPTRIC_DB_SCHEMA:
                self._configure_hive(connection)
                if self._expected_store_role is not None:
                    identity_row = connection.execute(
                        "SELECT value FROM meta WHERE key = 'store_identity_json'"
                    ).fetchone()
                    anchor_row = connection.execute(
                        "SELECT value FROM meta WHERE key = 'store_role_anchor_json'"
                    ).fetchone()
                    if identity_row is None and anchor_row is None:
                        raise StoreError(
                            "expected-role read has no store role anchor",
                            expected_role=self._expected_store_role,
                        )
                    for operation, row in (
                        ("expected-role read identity", identity_row),
                        ("expected-role read anchor", anchor_row),
                    ):
                        if row is None:
                            continue
                        try:
                            identity = json.loads(str(row["value"]))
                        except ValueError as exc:
                            raise StoreError(f"{operation} is malformed") from exc
                        self._validate_store_identity(identity, operation=operation)

    def _refresh_schema(self, connection: sqlite3.Connection) -> None:
        """Refresh a long-lived process after another process completes a migration."""

        schema = self._schema_version(connection)
        if schema not in (LEGACY_CONCEPTRIC_DB_SCHEMA, CONCEPTRIC_DB_SCHEMA):
            raise StoreError(
                "conceptric database schema is unknown",
                expected=[LEGACY_CONCEPTRIC_DB_SCHEMA, CONCEPTRIC_DB_SCHEMA],
                got=schema,
            )
        self.schema_version = schema
        if schema == CONCEPTRIC_DB_SCHEMA:
            self._configure_hive(connection)

    @staticmethod
    def _schema_version(connection: sqlite3.Connection) -> str | None:
        meta = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
        ).fetchone()
        if meta is None:
            return None
        row = connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        return None if row is None else str(row["value"])

    @staticmethod
    def _create_v2_schema(
        connection: sqlite3.Connection, *, hive_ref: str = DEFAULT_EVENT_HIVE_REF
    ) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY,
                previous_digest TEXT NOT NULL,
                record_digest TEXT NOT NULL UNIQUE,
                event_id TEXT NOT NULL UNIQUE,
                event_kind TEXT NOT NULL,
                assumption TEXT,
                fibre TEXT,
                event_handle TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_kind_idx
                ON events(event_kind, assumption, fibre);
            CREATE TABLE IF NOT EXISTS authority_checkpoint (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                checkpoint_json TEXT NOT NULL,
                checkpoint_digest TEXT NOT NULL
            ) WITHOUT ROWID;
            """
        )
        metadata = {
            "schema_version": CONCEPTRIC_DB_SCHEMA,
            "event_hive_ref": hive_ref,
            "event_hive_codec": CompressedHive.codec,
            "authoritative_head_digest": GENESIS_DIGEST,
        }
        for key, value in metadata.items():
            connection.execute("INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)", (key, value))
        got = ConceptricStore._schema_version(connection)
        if got != CONCEPTRIC_DB_SCHEMA:
            raise StoreError(
                "conceptric database schema is unknown", expected=CONCEPTRIC_DB_SCHEMA, got=got
            )

    @staticmethod
    def _normalize_authority_context(
        supplied: Mapping[str, str] | None,
        *,
        root: Path | None = None,
        store_role: str | None = None,
        extra_authority_files: tuple[Path, ...] = (),
    ) -> dict[str, str]:
        if supplied is None:
            supplied = ConceptricStore.authority_context_manifest(
                root or Path("."), store_role=store_role,
                extra_authority_files=extra_authority_files,
            )
        required = ("implementation_digest", "environment_root", "dirty_paths_root")
        normalized = {key: str(supplied.get(key, "")) for key in required}
        if any(not normalized[key].startswith("sha256:") for key in required):
            raise StoreError("authority checkpoint context requires three sha256 roots")
        return normalized

    @staticmethod
    def _anchored_store_role(connection: sqlite3.Connection) -> str | None:
        """Read one internally consistent optional role for default authority context."""

        identities = []
        for row in connection.execute(
            "SELECT value FROM meta WHERE key IN "
            "('store_identity_json', 'store_role_anchor_json')"
        ):
            try:
                identity = json.loads(str(row["value"]))
            except (TypeError, ValueError) as exc:
                raise HistoryChainMismatch("store role anchor is malformed") from exc
            if (
                not isinstance(identity, dict)
                or identity.get("schema_version") != "atlas.store-identity/1"
                or identity.get("database_ref") != "conceptric.sqlite3"
                or not isinstance(identity.get("role"), str)
                or not identity["role"].strip()
            ):
                raise HistoryChainMismatch("store role anchor shape is invalid")
            identities.append(identity)
        if not identities:
            return None
        if any(identity != identities[0] for identity in identities):
            raise HistoryChainMismatch("store identity and role anchor disagree")
        return str(identities[0]["role"])

    @classmethod
    def authority_context_manifest(
        cls,
        root: Path,
        *,
        store_role: str | None = None,
        allow_git_unavailable: bool = False,
        extra_authority_files: tuple[Path, ...] = (),
    ) -> dict[str, str]:
        """One shared exact authority-module/runtime/store manifest for every face."""

        evidence = cls.authority_context_evidence(
            root,
            store_role=store_role,
            allow_git_unavailable=allow_git_unavailable,
            extra_authority_files=extra_authority_files,
        )
        return dict(evidence["roots"])

    @classmethod
    def authority_context_evidence(
        cls,
        root: Path,
        *,
        store_role: str | None = None,
        allow_git_unavailable: bool = False,
        extra_authority_files: tuple[Path, ...] = (),
    ) -> dict[str, Any]:
        """Return the normalized source-bearing context and its three checkpoint roots."""

        files = {
            relative: hash_bytes(_authority_path(relative).read_bytes())
            for relative in _AUTHORITY_CONTEXT_RELATIVE_PATHS
        }
        if files != _LOADED_AUTHORITY_FILE_DIGESTS:
            raise StoreError(
                "authority context is UNKNOWN because loaded code differs from disk",
                loaded=_LOADED_AUTHORITY_FILE_DIGESTS,
                disk=files,
            )
        # Container keys stay relative to the container; external keys are caller paths
        # expressed against the same root, so neither the package nor its imports name hosts.
        files.update(_extra_authority_file_digests(extra_authority_files))
        manifest_paths = list(files)
        try:
            dirty_bytes = subprocess.run(
                [
                    "git",
                    "status",
                    "--porcelain=v1",
                    "-z",
                    "--untracked-files=all",
                    "--",
                    *manifest_paths,
                ],
                cwd=_AUTHORITY_CONTEXT_REPOSITORY,
                check=True,
                capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            if not (
                allow_git_unavailable
                and isinstance(store_role, str)
                and "fixture" in store_role.casefold()
            ):
                raise StoreError(
                    "authority context is UNKNOWN because Git state is unavailable",
                    store_role=store_role,
                ) from exc
            dirty_bytes = b"DECLARED-NO-GIT-FIXTURE"
        dirty = {
            "schema_version": "atlas.authority-dirty-paths/1",
            "manifest_paths": manifest_paths,
            "porcelain_v1_z_sha256": hash_bytes(dirty_bytes),
        }
        manifest = {
            "schema_version": "atlas.authority-context-manifest/1",
            "files": files,
            "runtime": {
                "python": platform.python_implementation(),
                "version": list(os.sys.version_info[:3]),
                "platform": platform.system(),
            },
            "store": {
                "root": os.fspath(Path(root).resolve()),
                "role": store_role,
                "ledger_schema": CONCEPTRIC_DB_SCHEMA,
            },
        }
        roots = {
            "implementation_digest": chash(
                {
                    "schema_version": "atlas.authority-implementation/1",
                    "files": files,
                }
            ),
            "environment_root": chash(manifest),
            "dirty_paths_root": chash(dirty),
        }
        return {
            "schema_version": "atlas.authority-context-evidence/1",
            "manifest": manifest,
            "dirty": dirty,
            "roots": roots,
            "evidence_root": chash(
                {
                    "schema_version": "atlas.authority-context-evidence/1",
                    "manifest": manifest,
                    "dirty": dirty,
                    "roots": roots,
                }
            ),
        }

    def _checkpoint_for_state(
        self,
        state: ConceptricState,
        *,
        head_record_digest: str,
    ) -> AuthorityCheckpoint:
        return AuthorityCheckpoint(
            cursor=state.event_count,
            head_event_id=state.head_event_id,
            head_record_digest=head_record_digest,
            implementation_digest=self._authority_context["implementation_digest"],
            environment_root=self._authority_context["environment_root"],
            dirty_paths_root=self._authority_context["dirty_paths_root"],
            authority=authority_checkpoint_projection(state),
        )

    @staticmethod
    def _write_checkpoint(
        connection: sqlite3.Connection,
        checkpoint: AuthorityCheckpoint,
    ) -> str:
        # A checkpoint is a derived, head-bound read accelerator.  It may be absent or stale
        # after an ordinary local source change; that must not turn a valid locked append into a
        # provider/holder adoption ceremony.  Recreate and refresh it in the same ledger
        # transaction as the exact event packet.
        connection.execute(
            "CREATE TABLE IF NOT EXISTS authority_checkpoint ("
            "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
            "checkpoint_json TEXT NOT NULL, checkpoint_digest TEXT NOT NULL"
            ") WITHOUT ROWID"
        )
        body = checkpoint.to_dict()
        digest = chash(body)
        connection.execute(
            "INSERT OR REPLACE INTO authority_checkpoint"
            "(singleton, checkpoint_json, checkpoint_digest) VALUES (1, ?, ?)",
            (canonical_json(body), digest),
        )
        return digest

    @classmethod
    def prepare_authority_checkpoint(
        cls,
        root: Path,
        *,
        expected_predecessor: str,
        authority_context: Mapping[str, str],
        expected_store_role: str | None = None,
        extra_authority_files: tuple[Path, ...] = (),
        reason: str = "explicit stopped-writer authority adoption",
    ) -> dict[str, Any]:
        """Exclusively CAS one stopped-writer checkpoint adoption or context rebind."""

        reason = str(reason).strip()
        if not reason:
            raise StoreError("authority checkpoint adoption requires a reason")

        # A read-only construction verifies store identity and schema without repairing either
        # ledger or projection.  Only after that no-effect admission do we switch this private
        # face to a writable SQLite connection under the exclusive store lock.
        store = cls(
            Path(root),
            read_only=True,
            authority_context=authority_context,
            expected_store_role=expected_store_role,
            extra_authority_files=extra_authority_files,
        )
        store.read_only = False
        fresh_context = cls.authority_context_manifest(
            store.root, store_role=expected_store_role,
            extra_authority_files=extra_authority_files,
        )
        if dict(authority_context) != fresh_context:
            raise HistoryChainMismatch(
                "authority checkpoint adoption context is not the loaded disk generation",
                supplied=dict(authority_context),
                current=fresh_context,
            )
        with store._locked(), store._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                store._refresh_schema(connection)
                if store.schema_version != CONCEPTRIC_DB_SCHEMA:
                    raise StoreError("authority checkpoint adoption requires hived schema v2")
                rows = store._read_v2_rows_from(connection)
                state = store._fold(rows)
                head = store._head_digest(rows)
                table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='authority_checkpoint'"
                ).fetchone()
                existing_checkpoint: AuthorityCheckpoint | None = None
                predecessor_cursor = 0
                if table is None:
                    actual_predecessor = head
                else:
                    existing = connection.execute(
                        "SELECT checkpoint_json, checkpoint_digest "
                        "FROM authority_checkpoint WHERE singleton = 1"
                    ).fetchone()
                    if existing is None:
                        raise HistoryChainMismatch(
                            "authority checkpoint adoption found an empty checkpoint table"
                        )
                    try:
                        existing_body = json.loads(str(existing["checkpoint_json"]))
                    except (TypeError, ValueError) as exc:
                        raise HistoryChainMismatch(
                            "authority checkpoint adoption predecessor is malformed"
                        ) from exc
                    if canonical_json(existing_body) != str(existing["checkpoint_json"]):
                        raise HistoryChainMismatch(
                            "authority checkpoint adoption predecessor is not canonical JSON"
                        )
                    actual_predecessor = chash(existing_body)
                    if actual_predecessor != str(existing["checkpoint_digest"]):
                        raise HistoryChainMismatch(
                            "authority checkpoint adoption predecessor digest does not verify"
                        )
                    try:
                        existing_checkpoint = AuthorityCheckpoint.from_dict(existing_body)
                    except (TypeError, ValueError) as exc:
                        raise HistoryChainMismatch(
                            "authority checkpoint adoption predecessor shape is invalid"
                        ) from exc
                    predecessor_cursor = existing_checkpoint.cursor
                    if existing_checkpoint.cursor > len(rows):
                        raise HistoryChainMismatch(
                            "authority checkpoint adoption predecessor is beyond the ledger head"
                        )
                    if existing_checkpoint.cursor == 0:
                        prefix_coordinate = (None, GENESIS_DIGEST)
                    else:
                        prefix = rows[existing_checkpoint.cursor - 1]
                        prefix_coordinate = (prefix.event.event_id, prefix.record_digest)
                    if (
                        existing_checkpoint.head_event_id,
                        existing_checkpoint.head_record_digest,
                    ) != prefix_coordinate:
                        raise HistoryChainMismatch(
                            "authority checkpoint adoption predecessor is not on the ledger prefix"
                        )
                if expected_predecessor != actual_predecessor:
                    raise HistoryChainMismatch(
                        "authority checkpoint adoption predecessor moved",
                        expected=expected_predecessor,
                        actual=actual_predecessor,
                    )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS authority_checkpoint ("
                    "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
                    "checkpoint_json TEXT NOT NULL, checkpoint_digest TEXT NOT NULL"
                    ") WITHOUT ROWID"
                )
                store._authority_context = fresh_context
                checkpoint = store._checkpoint_for_state(state, head_record_digest=head)
                digest = store._write_checkpoint(connection, checkpoint)
                receipt = {
                    "schema_version": "atlas.authority-checkpoint-adoption/2",
                    "status": "READY",
                    "beat": "ATLAS-AUTHORITY-RE-ADOPTION",
                    "reason": reason,
                    "predecessor": actual_predecessor,
                    "checkpoint_digest": digest,
                    "cursor": checkpoint.cursor,
                    "head_record_digest": checkpoint.head_record_digest,
                    "authority_context": fresh_context,
                    "event_append": False,
                    "ledger_checkpoint_write": True,
                    "ledger_wal_checkpoint_required": True,
                    "deep_prefix_verified": True,
                    "writer_precondition": "exclusive store lock",
                    "cost": {
                        "schema_version": "atlas.authority-re-adoption-cost/1",
                        "unit": "ledger-events",
                        "diff": checkpoint.cursor - predecessor_cursor,
                        "rows_verified": len(rows),
                        "reason": reason,
                    },
                    "ordering_rule": (
                        "land code touching errors.py/history.py/ids.py/state.py/store.py -> "
                        "re-adopt every store -> measure"
                    ),
                }
                receipt_handle = chash(receipt)
                # Bank the predecessor and result atomically with the checkpoint. Historical
                # adoptions survive later appends and context changes under their own handles.
                receipt_key = "authority_checkpoint_adoption:" + receipt_handle
                connection.execute(
                    "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
                    (receipt_key, canonical_json(receipt)),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            wal_checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if wal_checkpoint is None or int(wal_checkpoint[0]) != 0:
                raise StoreError(
                    "authority re-adoption committed but WAL checkpoint is busy",
                    wal_checkpoint=(None if wal_checkpoint is None else tuple(wal_checkpoint)),
                )
        return {
            **receipt,
            "receipt_handle": receipt_handle,
            "receipt_key": receipt_key,
            "wal_checkpoint": tuple(wal_checkpoint),
        }

    @staticmethod
    def _validate_authority_context_evidence(
        evidence: Any,
        *,
        field: str,
    ) -> dict[str, Any]:
        if not isinstance(evidence, dict) or set(evidence) != {
            "schema_version",
            "manifest",
            "dirty",
            "roots",
            "evidence_root",
        }:
            raise StoreError(
                "portable authority adoption context evidence is malformed",
                field=field,
            )
        manifest = evidence.get("manifest")
        dirty = evidence.get("dirty")
        roots = evidence.get("roots")
        if (
            not isinstance(manifest, dict)
            or set(manifest) != {"schema_version", "files", "runtime", "store"}
            or manifest.get("schema_version") != "atlas.authority-context-manifest/1"
            or not isinstance(manifest.get("files"), dict)
            or not isinstance(manifest.get("runtime"), dict)
            or not isinstance(manifest.get("store"), dict)
            or not isinstance(dirty, dict)
            or not isinstance(roots, dict)
        ):
            raise StoreError(
                "portable authority adoption context manifest is malformed",
                field=field,
            )
        runtime = manifest["runtime"]
        store = manifest["store"]
        version = runtime.get("version")
        if (
            set(runtime) != {"python", "version", "platform"}
            or not isinstance(runtime.get("python"), str)
            or not isinstance(runtime.get("platform"), str)
            or not isinstance(version, list)
            or len(version) != 3
            or any(isinstance(part, bool) or not isinstance(part, int) for part in version)
            or set(store) != {"root", "role", "ledger_schema"}
            or not isinstance(store.get("root"), str)
            or not isinstance(store.get("role"), str)
            or not isinstance(store.get("ledger_schema"), str)
            or set(dirty)
            != {"schema_version", "manifest_paths", "porcelain_v1_z_sha256"}
            or dirty.get("schema_version") != "atlas.authority-dirty-paths/1"
            or not isinstance(dirty.get("manifest_paths"), list)
            or any(not isinstance(path, str) for path in dirty["manifest_paths"])
            or not isinstance(dirty.get("porcelain_v1_z_sha256"), str)
            or set(roots)
            != {"implementation_digest", "environment_root", "dirty_paths_root"}
        ):
            raise StoreError(
                "portable authority adoption context manifest fields are malformed",
                field=field,
            )
        files = manifest["files"]
        if any(
            not isinstance(path, str)
            or not isinstance(digest, str)
            or not digest.startswith(HASH_PREFIX)
            for path, digest in files.items()
        ):
            raise StoreError(
                "portable authority adoption context file manifest is malformed",
                field=field,
            )
        expected_roots = {
            "implementation_digest": chash(
                {
                    "schema_version": "atlas.authority-implementation/1",
                    "files": files,
                }
            ),
            "environment_root": chash(manifest),
            "dirty_paths_root": chash(dirty),
        }
        if roots != expected_roots:
            raise StoreError(
                "portable authority adoption context component roots do not verify",
                field=field,
            )
        body = {key: value for key, value in evidence.items() if key != "evidence_root"}
        if evidence.get("schema_version") != "atlas.authority-context-evidence/1" or chash(
            body
        ) != evidence.get("evidence_root"):
            raise StoreError(
                "portable authority adoption context evidence does not verify",
                field=field,
            )
        return dict(evidence)

    @classmethod
    def _verify_portable_authority_context_relocation(
        cls,
        source_evidence: Any,
        target_evidence: Any,
        *,
        destination_root: Path | str | None = None,
    ) -> dict[str, Any]:
        """Prove that moving the canonical store root is the only context change."""

        source = cls._validate_authority_context_evidence(
            source_evidence,
            field="source_authority_context_evidence",
        )
        target = cls._validate_authority_context_evidence(
            target_evidence,
            field="target_context_evidence",
        )
        source_manifest = source.get("manifest")
        target_manifest = target.get("manifest")
        source_store = (
            None if not isinstance(source_manifest, dict) else source_manifest.get("store")
        )
        target_store = (
            None if not isinstance(target_manifest, dict) else target_manifest.get("store")
        )
        if not all(
            isinstance(value, dict)
            for value in (source_manifest, target_manifest, source_store, target_store)
        ):
            raise StoreError("portable authority context manifest is malformed")
        target_root = target_store.get("root")
        if not isinstance(target_root, str):
            raise StoreError("portable authority context destination root is malformed")
        if destination_root is not None:
            expected_root = os.fspath(Path(destination_root).expanduser().resolve())
            if target_root != expected_root:
                raise HistoryChainMismatch(
                    "portable authority context destination root moved",
                    expected=expected_root,
                    actual=target_root,
                )

        relocated_manifest = dict(source_manifest)
        relocated_store = dict(source_store)
        source_root = relocated_store.get("root")
        relocated_store["root"] = target_root
        relocated_manifest["store"] = relocated_store
        relocated_roots = dict(source.get("roots") or {})
        relocated_roots["environment_root"] = chash(relocated_manifest)
        relocated = {
            "schema_version": source["schema_version"],
            "manifest": relocated_manifest,
            "dirty": source.get("dirty"),
            "roots": relocated_roots,
        }
        relocated["evidence_root"] = chash(relocated)
        if relocated != target:
            raise HistoryChainMismatch(
                "portable authority context relocation is not root-only",
                source_root=source_root,
                destination_root=target_root,
                source_evidence_root=source.get("evidence_root"),
                expected_target_evidence_root=relocated["evidence_root"],
                actual_target_evidence_root=target.get("evidence_root"),
            )
        return {
            "schema_version": "atlas.portable-authority-context-relocation/1",
            "source_root": source_root,
            "destination_root": target_root,
            "source_evidence_root": source["evidence_root"],
            "destination_evidence_root": target["evidence_root"],
            "relocated_environment_root": relocated_roots["environment_root"],
            "changed_fields": [
                "manifest.store.root",
                "roots.environment_root",
                "evidence_root",
            ],
        }

    @staticmethod
    def _validate_portable_authority_adoption(raw: Any) -> dict[str, Any]:
        """Strictly parse the durable source-snapshot -> local-checkpoint receipt."""

        if not isinstance(raw, dict):
            raise StoreError("portable authority adoption receipt is not an object")
        expected_keys = {
            "schema_version",
            "status",
            "source_snapshot_id",
            "source_receipt_sha256",
            "source_ledger_sha256",
            "source_checkpoint_digest",
            "source_cursor",
            "source_head_event_id",
            "source_head_record_digest",
            "source_blob_manifest_root",
            "source_event_hive_manifest_root",
            "source_evidence_manifest_root",
            "source_authority_context_evidence",
            "source_git_commit",
            "source_git_tree",
            "recovery_coordinate_payload_digest",
            "predecessor_adoption_root",
            "grant_root",
            "grant_identity",
            "target_store_identity",
            "target_context",
            "target_context_evidence",
            "target_checkpoint_digest",
            "event_append",
            "integrity_boundary",
        }
        if set(raw) != expected_keys:
            raise StoreError(
                "portable authority adoption receipt shape is unknown",
                expected=sorted(expected_keys),
                got=sorted(str(key) for key in raw),
            )
        if raw.get("schema_version") != PORTABLE_AUTHORITY_ADOPTION_SCHEMA:
            raise StoreError("portable authority adoption receipt schema is unknown")
        if raw.get("status") != "ADOPTED" or raw.get("event_append") is not False:
            raise StoreError("portable authority adoption receipt claims an unknown transition")
        if raw.get("integrity_boundary") != "CHECKSUMMED-CRUTCH":
            raise StoreError("portable authority adoption overstates checkpoint integrity")
        for field in (
            "source_snapshot_id",
            "source_receipt_sha256",
            "source_ledger_sha256",
            "source_checkpoint_digest",
            "source_head_record_digest",
            "source_blob_manifest_root",
            "source_event_hive_manifest_root",
            "source_evidence_manifest_root",
            "recovery_coordinate_payload_digest",
            "predecessor_adoption_root",
            "grant_root",
            "target_checkpoint_digest",
        ):
            value = raw.get(field)
            if (
                not isinstance(value, str)
                or not value.startswith(HASH_PREFIX)
                or len(value) != len(HASH_PREFIX) + 64
            ):
                raise StoreError(
                    "portable authority adoption digest is malformed", field=field
                )
        cursor = raw.get("source_cursor")
        if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
            raise StoreError("portable authority adoption cursor is malformed")
        head_event_id = raw.get("source_head_event_id")
        if head_event_id is not None and (
            not isinstance(head_event_id, str)
            or not head_event_id.startswith(HASH_PREFIX)
            or len(head_event_id) != len(HASH_PREFIX) + 64
        ):
            raise StoreError("portable authority adoption head event is malformed")
        context = raw.get("target_context")
        normalized_context = ConceptricStore._normalize_authority_context(context)
        if context != normalized_context:
            raise StoreError("portable authority adoption context is not canonical")
        source_evidence = ConceptricStore._validate_authority_context_evidence(
            raw.get("source_authority_context_evidence"),
            field="source_authority_context_evidence",
        )
        target_evidence = ConceptricStore._validate_authority_context_evidence(
            raw.get("target_context_evidence"),
            field="target_context_evidence",
        )
        if target_evidence.get("roots") != context:
            raise StoreError("portable authority adoption target context evidence moved")
        ConceptricStore._verify_portable_authority_context_relocation(
            source_evidence,
            target_evidence,
            destination_root=(target_evidence.get("manifest") or {}).get("store", {}).get(
                "root"
            ),
        )
        for field in ("source_git_commit", "source_git_tree"):
            value = raw.get(field)
            if (
                not isinstance(value, str)
                or len(value) != 40
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise StoreError("portable authority adoption Git identity is malformed", field=field)
        grant = raw.get("grant_identity")
        if not isinstance(grant, dict) or grant.get("schema_version") != (
            "laplace.portable-runtime-adoption-grant/1"
        ):
            raise StoreError("portable authority adoption grant identity is malformed")
        if chash(grant) != raw.get("grant_root"):
            raise StoreError("portable authority adoption grant root does not verify")
        grant_expected = {
            "source_snapshot_id": raw.get("source_snapshot_id"),
            "source_receipt_sha256": raw.get("source_receipt_sha256"),
            "source_checkpoint_digest": raw.get("source_checkpoint_digest"),
            "recovery_coordinate_payload_digest": raw.get(
                "recovery_coordinate_payload_digest"
            ),
            "destination_context_evidence_root": (
                raw["target_context_evidence"].get("evidence_root")
            ),
            "target_store_role": (
                (raw.get("target_store_identity") or {}).get("role")
            ),
            "target_store_schema": CONCEPTRIC_DB_SCHEMA,
            "predecessor_adoption_root": raw.get("predecessor_adoption_root"),
        }
        grant_mismatches = {
            field: {"expected": value, "got": grant.get(field)}
            for field, value in grant_expected.items()
            if grant.get(field) != value
        }
        destination_root = (
            ((raw["target_context_evidence"].get("manifest") or {}).get("store") or {}).get(
                "root"
            )
        )
        if grant.get("destination_root") != destination_root:
            grant_mismatches["destination_root"] = {
                "expected": destination_root,
                "got": grant.get("destination_root"),
            }
        if grant_mismatches:
            raise StoreError(
                "portable authority adoption grant contradicts its adoption",
                mismatches=grant_mismatches,
            )
        identity = raw.get("target_store_identity")
        if not isinstance(identity, dict):
            raise StoreError("portable authority adoption store identity is malformed")
        return dict(raw)

    @classmethod
    def read_portable_authority_adoption(
        cls,
        root: Path,
        *,
        expected_store_role: str,
        extra_authority_files: tuple[Path, ...] = (),
    ) -> dict[str, Any] | None:
        """Read the keyed adoption receipt without repairing or adopting the store."""

        store = cls(
            Path(root),
            read_only=True,
            expected_store_role=expected_store_role,
            authority_context=cls.authority_context_manifest(
                Path(root), store_role=expected_store_role,
                extra_authority_files=extra_authority_files,
            ),
            extra_authority_files=extra_authority_files,
        )
        with store._locked(shared=True), store._connect() as connection:
            row = connection.execute(
                "SELECT value FROM meta WHERE key = ?",
                (PORTABLE_AUTHORITY_ADOPTION_META_KEY,),
            ).fetchone()
        if row is None:
            return None
        try:
            body = json.loads(str(row["value"]))
        except (TypeError, ValueError) as exc:
            raise StoreError("portable authority adoption receipt is malformed") from exc
        if canonical_json(body) != str(row["value"]):
            raise StoreError("portable authority adoption receipt is not canonical JSON")
        receipt = cls._validate_portable_authority_adoption(body)
        store._validate_store_identity(
            receipt["target_store_identity"], operation="portable authority adoption"
        )
        return receipt

    @classmethod
    def prepare_portable_authority_checkpoint(
        cls,
        root: Path,
        *,
        expected_predecessor: str,
        authority_context: Mapping[str, str],
        expected_store_role: str,
        source_snapshot_id: str,
        source_receipt_sha256: str,
        source_ledger_sha256: str,
        source_cursor: int,
        source_head_event_id: str | None,
        source_head_record_digest: str,
        source_blob_manifest_root: str,
        source_event_hive_manifest_root: str,
        source_evidence_manifest_root: str,
        source_authority_context_evidence: Mapping[str, Any],
        source_git_commit: str,
        source_git_tree: str,
        recovery_coordinate_payload_digest: str,
        predecessor_adoption_root: str,
        grant_root: str,
        grant_identity: Mapping[str, Any],
        target_context_evidence: Mapping[str, Any],
        target_canonical_root: Path,
        extra_authority_files: tuple[Path, ...] = (),
    ) -> dict[str, Any]:
        """CAS one verified travelling snapshot onto this filesystem/runtime root.

        The portable receipt and replacement checkpoint commit in one SQLite transaction.
        Consequently a crash exposes either the exact source snapshot or a complete, keyed
        adoption which can be custody-resealed idempotently; it can never expose an anonymous
        rebind.  The adjacent-checksum C2a boundary remains explicit.
        """

        source_identity = {
            "source_snapshot_id": source_snapshot_id,
            "source_receipt_sha256": source_receipt_sha256,
            "source_ledger_sha256": source_ledger_sha256,
            "source_cursor": source_cursor,
            "source_head_event_id": source_head_event_id,
            "source_head_record_digest": source_head_record_digest,
            "source_blob_manifest_root": source_blob_manifest_root,
            "source_event_hive_manifest_root": source_event_hive_manifest_root,
            "source_evidence_manifest_root": source_evidence_manifest_root,
            "source_authority_context_evidence": dict(source_authority_context_evidence),
            "source_git_commit": source_git_commit,
            "source_git_tree": source_git_tree,
            "recovery_coordinate_payload_digest": recovery_coordinate_payload_digest,
            "predecessor_adoption_root": predecessor_adoption_root,
            "grant_root": grant_root,
            "grant_identity": dict(grant_identity),
        }
        # Reuse the strict receipt parser for all scalar source fields before opening writable.
        probe = {
            "schema_version": PORTABLE_AUTHORITY_ADOPTION_SCHEMA,
            "status": "ADOPTED",
            **source_identity,
            "source_checkpoint_digest": expected_predecessor,
            "target_store_identity": {
                "schema_version": "atlas.store-identity/1",
                "role": expected_store_role,
                "database_ref": "conceptric.sqlite3",
            },
            "target_context": dict(authority_context),
            "target_context_evidence": dict(target_context_evidence),
            "target_checkpoint_digest": expected_predecessor,
            "event_append": False,
            "integrity_boundary": "CHECKSUMMED-CRUTCH",
        }
        cls._validate_portable_authority_adoption(probe)

        store = cls(
            Path(root),
            read_only=True,
            expected_store_role=expected_store_role,
            authority_context=authority_context,
            extra_authority_files=extra_authority_files,
        )
        # Capture the immutable snapshot main before the explicit writable connection can
        # switch SQLite from DELETE to WAL journalling.  The journal-mode header change is part
        # of local adoption, not evidence that the supplied snapshot had different bytes.
        source_ledger_bytes = sha256_file(store.path)
        fresh_context_evidence = cls.authority_context_evidence(
            Path(target_canonical_root), store_role=expected_store_role,
            extra_authority_files=extra_authority_files,
        )
        fresh_context = dict(fresh_context_evidence["roots"])
        if dict(authority_context) != fresh_context:
            raise HistoryChainMismatch(
                "portable authority adoption context is not the loaded disk generation",
                supplied=dict(authority_context),
                current=fresh_context,
            )
        if dict(target_context_evidence) != fresh_context_evidence:
            raise HistoryChainMismatch(
                "portable authority adoption target evidence is not the loaded destination",
                supplied=dict(target_context_evidence),
                current=fresh_context_evidence,
            )
        cls._verify_portable_authority_context_relocation(
            source_authority_context_evidence,
            fresh_context_evidence,
            destination_root=target_canonical_root,
        )
        target_store_identity = {
            "schema_version": "atlas.store-identity/1",
            "role": expected_store_role,
            "database_ref": store.path.name,
        }
        # Refuse a stale predecessor or changed snapshot on the immutable read face. Opening a
        # writable SQLite connection can legitimately switch DELETE -> WAL journalling, so the
        # source CAS must pass before even that local header/sidecar effect is possible.
        with store._locked(shared=True), store._connect() as source_connection:
            preexisting_adoption = source_connection.execute(
                "SELECT value FROM meta WHERE key = ?",
                (PORTABLE_AUTHORITY_ADOPTION_META_KEY,),
            ).fetchone()
            source_checkpoint = source_connection.execute(
                "SELECT checkpoint_json, checkpoint_digest "
                "FROM authority_checkpoint WHERE singleton = 1"
            ).fetchone()
            if source_checkpoint is None:
                raise HistoryChainMismatch(
                    "portable authority adoption requires a verified source checkpoint"
                )
            if preexisting_adoption is None:
                actual_predecessor = str(source_checkpoint["checkpoint_digest"])
                if actual_predecessor != expected_predecessor:
                    raise HistoryChainMismatch(
                        "portable authority adoption predecessor moved",
                        expected=expected_predecessor,
                        actual=actual_predecessor,
                    )
                if source_ledger_bytes != source_ledger_sha256:
                    raise HistoryChainMismatch(
                        "portable authority adoption source ledger bytes moved",
                        expected=source_ledger_sha256,
                        actual=source_ledger_bytes,
                    )
        store.read_only = False
        with store._locked(), store._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                store._refresh_schema(connection)
                if store.schema_version != CONCEPTRIC_DB_SCHEMA:
                    raise StoreError("portable authority adoption requires hived schema v2")
                rows = store._read_v2_rows_from(connection)
                state = store._fold(rows)
                head = store._head_digest(rows)
                coordinate = {
                    "source_cursor": len(rows),
                    "source_head_event_id": state.head_event_id,
                    "source_head_record_digest": head,
                }
                requested_coordinate = {
                    key: source_identity[key]
                    for key in (
                        "source_cursor",
                        "source_head_event_id",
                        "source_head_record_digest",
                    )
                }
                if coordinate != requested_coordinate:
                    raise HistoryChainMismatch(
                        "portable authority adoption source coordinate moved",
                        expected=requested_coordinate,
                        actual=coordinate,
                    )
                existing_adoption_row = connection.execute(
                    "SELECT value FROM meta WHERE key = ?",
                    (PORTABLE_AUTHORITY_ADOPTION_META_KEY,),
                ).fetchone()
                existing_checkpoint_row = connection.execute(
                    "SELECT checkpoint_json, checkpoint_digest "
                    "FROM authority_checkpoint WHERE singleton = 1"
                ).fetchone()
                if existing_checkpoint_row is None:
                    raise HistoryChainMismatch(
                        "portable authority adoption requires a verified source checkpoint"
                    )
                if existing_adoption_row is not None:
                    try:
                        adoption_body = json.loads(str(existing_adoption_row["value"]))
                    except (TypeError, ValueError) as exc:
                        raise StoreError(
                            "portable authority adoption receipt is malformed"
                        ) from exc
                    existing_adoption = cls._validate_portable_authority_adoption(
                        adoption_body
                    )
                    requested = {
                        **source_identity,
                        "source_checkpoint_digest": expected_predecessor,
                        "target_store_identity": target_store_identity,
                        "target_context": fresh_context,
                        "target_context_evidence": fresh_context_evidence,
                    }
                    mismatches = {
                        key: {"expected": value, "recorded": existing_adoption.get(key)}
                        for key, value in requested.items()
                        if existing_adoption.get(key) != value
                    }
                    if mismatches:
                        raise HistoryChainMismatch(
                            "portable authority adoption retry names different custody",
                            mismatches=mismatches,
                        )
                    if str(existing_checkpoint_row["checkpoint_digest"]) != existing_adoption[
                        "target_checkpoint_digest"
                    ]:
                        raise HistoryChainMismatch(
                            "portable authority adoption checkpoint moved after commit"
                        )
                    connection.rollback()
                    return {
                        **existing_adoption,
                        "idempotent": True,
                        "ledger_checkpoint_write": False,
                    }

                try:
                    existing_body = json.loads(str(existing_checkpoint_row["checkpoint_json"]))
                    existing_checkpoint = AuthorityCheckpoint.from_dict(existing_body)
                except (TypeError, ValueError) as exc:
                    raise HistoryChainMismatch(
                        "portable authority adoption predecessor is malformed"
                    ) from exc
                actual_predecessor = chash(existing_body)
                if (
                    canonical_json(existing_body)
                    != str(existing_checkpoint_row["checkpoint_json"])
                    or actual_predecessor
                    != str(existing_checkpoint_row["checkpoint_digest"])
                ):
                    raise HistoryChainMismatch(
                        "portable authority adoption predecessor digest does not verify"
                    )
                if actual_predecessor != expected_predecessor:
                    raise HistoryChainMismatch(
                        "portable authority adoption predecessor moved",
                        expected=expected_predecessor,
                        actual=actual_predecessor,
                    )
                if (
                    existing_checkpoint.cursor,
                    existing_checkpoint.head_event_id,
                    existing_checkpoint.head_record_digest,
                ) != (len(rows), state.head_event_id, head):
                    raise HistoryChainMismatch(
                        "portable authority adoption predecessor is not the source head"
                    )
                if source_ledger_bytes != source_ledger_sha256:
                    raise HistoryChainMismatch(
                        "portable authority adoption source ledger bytes moved",
                        expected=source_ledger_sha256,
                        actual=source_ledger_bytes,
                    )
                store._authority_context = fresh_context
                checkpoint = store._checkpoint_for_state(state, head_record_digest=head)
                checkpoint_body = checkpoint.to_dict()
                checkpoint_digest = chash(checkpoint_body)
                adoption = {
                    "schema_version": PORTABLE_AUTHORITY_ADOPTION_SCHEMA,
                    "status": "ADOPTED",
                    **source_identity,
                    "source_checkpoint_digest": expected_predecessor,
                    "target_store_identity": target_store_identity,
                    "target_context": fresh_context,
                    "target_context_evidence": fresh_context_evidence,
                    "target_checkpoint_digest": checkpoint_digest,
                    "event_append": False,
                    "integrity_boundary": "CHECKSUMMED-CRUTCH",
                }
                cls._validate_portable_authority_adoption(adoption)
                connection.execute(
                    "INSERT INTO meta(key, value) VALUES (?, ?)",
                    (PORTABLE_AUTHORITY_ADOPTION_META_KEY, canonical_json(adoption)),
                )
                store._write_checkpoint(connection, checkpoint)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return {
            **adoption,
            "idempotent": False,
            "ledger_checkpoint_write": True,
        }

    @classmethod
    def seal_portable_authority_adoption(
        cls,
        root: Path,
        *,
        expected_store_role: str,
        expected_source_snapshot_id: str,
        expected_checkpoint_digest: str,
        expected_grant_root: str,
        target_canonical_root: Path,
        extra_authority_files: tuple[Path, ...] = (),
    ) -> dict[str, Any]:
        """Resume the post-CAS custody seal without relaxing ordinary writer admission."""

        adoption = cls.read_portable_authority_adoption(
            root, expected_store_role=expected_store_role,
            extra_authority_files=extra_authority_files,
        )
        if adoption is None:
            raise StoreError("portable authority adoption is absent")
        if (
            adoption["source_snapshot_id"] != expected_source_snapshot_id
            or adoption["target_checkpoint_digest"] != expected_checkpoint_digest
            or adoption["grant_root"] != expected_grant_root
        ):
            raise HistoryChainMismatch("portable authority adoption seal names different custody")
        context = dict(adoption["target_context"])
        current_evidence = cls.authority_context_evidence(
            Path(target_canonical_root), store_role=expected_store_role,
            extra_authority_files=extra_authority_files,
        )
        if current_evidence != adoption["target_context_evidence"]:
            raise HistoryChainMismatch(
                "portable authority adoption seal destination context moved"
            )
        store = cls(
            Path(root),
            read_only=True,
            expected_store_role=expected_store_role,
            authority_context=context,
            extra_authority_files=extra_authority_files,
        )
        store.read_only = False
        identity = store._validate_store_identity(
            adoption["target_store_identity"], operation="portable authority adoption seal"
        )
        with store._locked():
            return store._seal_custody_unlocked(identity)

    @staticmethod
    def _create_projection_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS objects (
                object_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content_handle TEXT NOT NULL,
                assumption TEXT,
                fibre TEXT,
                grade_contract_id TEXT NOT NULL,
                grade_coordinate_json TEXT NOT NULL,
                declared_event_id TEXT NOT NULL,
                object_json TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS edges (
                edge_id TEXT PRIMARY KEY,
                relation TEXT NOT NULL,
                source_object_id TEXT NOT NULL,
                target_object_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                assumption TEXT,
                fibre TEXT,
                operator TEXT NOT NULL,
                generation_handle TEXT NOT NULL,
                declared_event_id TEXT NOT NULL,
                edge_json TEXT NOT NULL,
                FOREIGN KEY(source_object_id) REFERENCES objects(object_id),
                FOREIGN KEY(target_object_id) REFERENCES objects(object_id)
            ) WITHOUT ROWID;
            CREATE INDEX IF NOT EXISTS edges_from_idx
                ON edges(source_object_id, relation, assumption, fibre);
            CREATE INDEX IF NOT EXISTS edges_to_idx
                ON edges(target_object_id, relation, assumption, fibre);
            CREATE INDEX IF NOT EXISTS objects_kind_idx
                ON objects(kind, assumption, fibre);
            CREATE INDEX IF NOT EXISTS objects_content_handle_idx
                ON objects(content_handle);
            CREATE TABLE IF NOT EXISTS development_reviews (
                commission_id TEXT PRIMARY KEY,
                assumption TEXT NOT NULL,
                fibre TEXT NOT NULL,
                commission_cursor INTEGER NOT NULL,
                commission_json TEXT NOT NULL,
                verdict_id TEXT,
                verdict_cursor INTEGER,
                verdict_json TEXT,
                review_decision TEXT,
                route_valid INTEGER NOT NULL,
                route_errors_json TEXT NOT NULL,
                residue_count INTEGER NOT NULL DEFAULT 0,
                latest_residue_json TEXT,
                is_terminal INTEGER NOT NULL
            ) WITHOUT ROWID;
            CREATE INDEX IF NOT EXISTS development_reviews_live_idx
                ON development_reviews(
                    assumption, fibre, is_terminal, commission_cursor DESC
                );
            CREATE TABLE IF NOT EXISTS development_review_counts (
                assumption TEXT NOT NULL,
                fibre TEXT NOT NULL,
                open_count INTEGER NOT NULL,
                terminal_count INTEGER NOT NULL,
                PRIMARY KEY(assumption, fibre)
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS seat_occupancy_projection (
                seat_id TEXT PRIMARY KEY,
                occupancy_json TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS provider_session_seat_projection (
                provider_session_ref TEXT NOT NULL,
                seat_id TEXT NOT NULL UNIQUE,
                occupancy_json TEXT NOT NULL,
                PRIMARY KEY(provider_session_ref, seat_id)
            ) WITHOUT ROWID;
            CREATE INDEX IF NOT EXISTS provider_session_seat_ref_idx
                ON provider_session_seat_projection(provider_session_ref);
            CREATE TABLE IF NOT EXISTS region_lease_projection (
                lease_id TEXT PRIMARY KEY,
                lease_json TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS seat_mail_pending (
                message_id TEXT PRIMARY KEY,
                recipient_seat_id TEXT NOT NULL,
                cursor INTEGER NOT NULL,
                message_state_json TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE INDEX IF NOT EXISTS seat_mail_pending_recipient_idx
                ON seat_mail_pending(recipient_seat_id, cursor);
            CREATE TABLE IF NOT EXISTS seat_mail_frontiers (
                seat_id TEXT PRIMARY KEY,
                revision_cursor INTEGER NOT NULL,
                revision_event_id TEXT NOT NULL,
                pending_count INTEGER NOT NULL,
                pending_tip_cursor INTEGER NOT NULL
            ) WITHOUT ROWID;
            """
        )

    @staticmethod
    def _project_seat_mail_record(
        connection: sqlite3.Connection,
        record: Any,
        *,
        event_id: str,
        event_cursor: int,
    ) -> None:
        """Advance only one recipient's disposable nonterminal-mail frontier."""

        message = record.message
        if record.status.value in {"queued", "pulled"}:
            connection.execute(
                """
                INSERT INTO seat_mail_pending(
                    message_id, recipient_seat_id, cursor, message_state_json
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    recipient_seat_id = excluded.recipient_seat_id,
                    cursor = excluded.cursor,
                    message_state_json = excluded.message_state_json
                """,
                (
                    message.message_id,
                    message.recipient_seat_id,
                    message.cursor,
                    canonical_json(record.to_dict()),
                ),
            )
        else:
            connection.execute(
                "DELETE FROM seat_mail_pending WHERE message_id = ?",
                (message.message_id,),
            )
        aggregate = connection.execute(
            "SELECT COUNT(*) AS pending_count, COALESCE(MAX(cursor), 0) AS pending_tip "
            "FROM seat_mail_pending WHERE recipient_seat_id = ?",
            (message.recipient_seat_id,),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO seat_mail_frontiers(
                seat_id, revision_cursor, revision_event_id,
                pending_count, pending_tip_cursor
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(seat_id) DO UPDATE SET
                revision_cursor = excluded.revision_cursor,
                revision_event_id = excluded.revision_event_id,
                pending_count = excluded.pending_count,
                pending_tip_cursor = excluded.pending_tip_cursor
            """,
            (
                message.recipient_seat_id,
                event_cursor,
                event_id,
                int(aggregate["pending_count"]),
                int(aggregate["pending_tip"]),
            ),
        )

    @staticmethod
    def _exact_review_commission(record: Any) -> bool:
        message = record.message
        roots = message.dependency_roots
        return message.message_type.endswith("commission") and all(
            bool(str(roots.get(key, "")))
            for key in (
                "frozen_commit",
                "frozen_tree",
                "frozen_diff_sha256",
            )
        )

    @staticmethod
    def _review_verdict_commission_id(record: Any) -> str | None:
        message = record.message
        commission_id = str(message.dependency_roots.get("commission", ""))
        if "verdict" not in message.message_type or not commission_id:
            return None
        return commission_id

    @staticmethod
    def _review_route(
        commission: SeatMessage, verdict: SeatMessage
    ) -> tuple[bool, tuple[str, ...]]:
        errors: list[str] = []
        if verdict.sender_seat_id != commission.recipient_seat_id:
            errors.append("verdict sender is not the commissioned reviewer")
        if verdict.recipient_seat_id != commission.sender_seat_id:
            errors.append("verdict recipient is not the commissioning builder")
        if verdict.sender_seat_id == commission.sender_seat_id:
            errors.append("builder cannot review its own publication")
        if verdict.cursor <= commission.cursor:
            errors.append("verdict does not follow its commission")
        for key in ("frozen_commit", "frozen_tree", "frozen_diff_sha256"):
            if str(verdict.dependency_roots.get(key, "")) != str(
                commission.dependency_roots.get(key, "")
            ):
                errors.append(f"verdict {key} disagrees with its commission")
        return not errors, tuple(errors)

    @staticmethod
    def _review_decision(record: Any) -> str | None:
        decision = str(record.message.dependency_roots.get("review_decision", "")).upper()
        if decision in {"ACCEPT", "REJECT", "CONTEST"}:
            return decision
        return LEGACY_UNTYPED_REVIEW_DECISIONS.get(record.message.message_id)

    @staticmethod
    def _adjust_review_counts(
        connection: sqlite3.Connection,
        *,
        assumption: str,
        fibre: str,
        old_terminal: bool | None,
        new_terminal: bool,
    ) -> None:
        if old_terminal is None:
            open_delta = 0 if new_terminal else 1
            terminal_delta = 1 if new_terminal else 0
        elif old_terminal == new_terminal:
            return
        else:
            open_delta = -1 if new_terminal else 1
            terminal_delta = 1 if new_terminal else -1
        connection.execute(
            """
            INSERT INTO development_review_counts(
                assumption, fibre, open_count, terminal_count
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(assumption, fibre) DO UPDATE SET
                open_count = open_count + excluded.open_count,
                terminal_count = terminal_count + excluded.terminal_count
            """,
            (assumption, fibre, open_delta, terminal_delta),
        )

    @staticmethod
    def _remove_review_count(
        connection: sqlite3.Connection,
        *,
        assumption: str,
        fibre: str,
        terminal: bool,
    ) -> None:
        column = "terminal_count" if terminal else "open_count"
        changed = connection.execute(
            f"UPDATE development_review_counts SET {column} = {column} - 1 "
            f"WHERE assumption = ? AND fibre = ? AND {column} > 0",
            (assumption, fibre),
        )
        if changed.rowcount != 1:
            raise HistoryChainMismatch(
                "development review count cannot remove its projected row",
                assumption=assumption,
                fibre=fibre,
                terminal=terminal,
            )
        connection.execute(
            "DELETE FROM development_review_counts "
            "WHERE assumption = ? AND fibre = ? "
            "AND open_count = 0 AND terminal_count = 0",
            (assumption, fibre),
        )

    @classmethod
    def _project_review_record(cls, connection: sqlite3.Connection, record: Any) -> None:
        """Advance one replaceable review row from an immutable message state."""

        if cls._exact_review_commission(record):
            message = record.message
            existing = connection.execute(
                "SELECT assumption, fibre, is_terminal FROM development_reviews "
                "WHERE commission_id = ?",
                (message.message_id,),
            ).fetchone()
            if record.status.value == "superseded":
                if existing is not None:
                    cls._remove_review_count(
                        connection,
                        assumption=str(existing["assumption"]),
                        fibre=str(existing["fibre"]),
                        terminal=bool(existing["is_terminal"]),
                    )
                    connection.execute(
                        "DELETE FROM development_reviews WHERE commission_id = ?",
                        (message.message_id,),
                    )
                return
            old_terminal = None if existing is None else bool(existing["is_terminal"])
            connection.execute(
                """
                INSERT INTO development_reviews(
                    commission_id, assumption, fibre, commission_cursor,
                    commission_json, verdict_id, verdict_cursor, verdict_json,
                    review_decision, route_valid, route_errors_json,
                    residue_count, latest_residue_json, is_terminal
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, 0, '[]', 0, NULL, 0)
                ON CONFLICT(commission_id) DO UPDATE SET
                    commission_json = excluded.commission_json
                """,
                (
                    message.message_id,
                    record.assumption,
                    record.fibre,
                    message.cursor,
                    canonical_json(record.to_dict()),
                ),
            )
            cls._adjust_review_counts(
                connection,
                assumption=record.assumption,
                fibre=record.fibre,
                old_terminal=old_terminal,
                new_terminal=old_terminal if old_terminal is not None else False,
            )
            return

        commission_id = cls._review_verdict_commission_id(record)
        if commission_id is None:
            return
        current = connection.execute(
            "SELECT * FROM development_reviews WHERE commission_id = ?",
            (commission_id,),
        ).fetchone()
        # A verdict sent before its alleged commission never becomes valid merely because a
        # later publication reuses the guessed id.  The append-order projection ignores it.
        if current is None:
            return
        verdict = record.message
        prior_cursor = current["verdict_cursor"]
        if prior_cursor is not None and verdict.cursor < int(prior_cursor):
            return
        commission_state = json.loads(str(current["commission_json"]))
        commission_message = SeatMessage.from_dict(commission_state["message"])
        route_valid, route_errors = cls._review_route(commission_message, verdict)
        decision = cls._review_decision(record)
        terminal = bool(route_valid and record.status.value == "delivered" and decision is not None)
        old_terminal = bool(current["is_terminal"])
        # The primary verdict slot is the latest evidence that is actually eligible to decide
        # this commission.  An uncommissioned seat, a malformed decision, or evidence arriving
        # after a valid delivered closure is residue: it must remain visible, but it may not
        # reopen or rewrite the accepted reverse route.
        preserves_closure = old_terminal and (
            current["verdict_id"] != verdict.message_id or not terminal
        )
        legacy_untyped = verdict.message_id in LEGACY_UNTYPED_REVIEW_VERDICT_IDS
        invalid_attempt = (
            not route_valid or (decision is None and not legacy_untyped) or preserves_closure
        )
        if invalid_attempt:
            reason = list(route_errors)
            if decision is None and not legacy_untyped:
                reason.append("verdict has no typed review decision")
            if preserves_closure:
                reason.append("later evidence cannot replace a valid delivered closure")
            residue = {
                "message": record.to_dict(),
                "route_valid": route_valid,
                "route_errors": reason,
                "review_decision": decision,
            }
            prior_residue = (
                None
                if current["latest_residue_json"] is None
                else json.loads(str(current["latest_residue_json"]))
            )
            prior_residue_id = (
                None
                if not isinstance(prior_residue, dict)
                else (prior_residue.get("message") or {}).get("message", {}).get("message_id")
            )
            connection.execute(
                """
                UPDATE development_reviews SET
                    residue_count = residue_count + ?,
                    latest_residue_json = ?
                WHERE commission_id = ?
                """,
                (
                    0 if prior_residue_id == verdict.message_id else 1,
                    canonical_json(residue),
                    commission_id,
                ),
            )
            return
        connection.execute(
            """
            UPDATE development_reviews SET
                verdict_id = ?, verdict_cursor = ?, verdict_json = ?,
                review_decision = ?, route_valid = ?, route_errors_json = ?,
                is_terminal = ?
            WHERE commission_id = ?
            """,
            (
                verdict.message_id,
                verdict.cursor,
                canonical_json(record.to_dict()),
                decision,
                int(route_valid),
                canonical_json(list(route_errors)),
                int(terminal),
                commission_id,
            ),
        )
        cls._adjust_review_counts(
            connection,
            assumption=str(current["assumption"]),
            fibre=str(current["fibre"]),
            old_terminal=old_terminal,
            new_terminal=terminal,
        )

    def _configure_hive(self, connection: sqlite3.Connection) -> None:
        ref_row = connection.execute(
            "SELECT value FROM meta WHERE key = 'event_hive_ref'"
        ).fetchone()
        codec_row = connection.execute(
            "SELECT value FROM meta WHERE key = 'event_hive_codec'"
        ).fetchone()
        if ref_row is None or codec_row is None or codec_row["value"] != CompressedHive.codec:
            raise StoreError("conceptric event hive metadata is missing or unknown")
        ref = Path(ref_row["value"])
        recorded = ref if ref.is_absolute() else self.root / ref
        requested = self._requested_hive_root
        if requested is not None and requested.resolve() != recorded.resolve():
            raise StoreError(
                "requested event hive disagrees with the ledger",
                requested=str(requested),
                recorded=str(recorded),
            )
        self.hive_root = recorded
        self.hive = CompressedHive(recorded)

    @staticmethod
    def _hive_ref(root: Path, hive_root: Path) -> str:
        try:
            return str(hive_root.resolve().relative_to(root.resolve()))
        except ValueError:
            return str(hive_root.resolve())

    def _legacy_rows(self) -> tuple[StoredEvent, ...]:
        try:
            raw_rows = tuple(read_jsonl(self.legacy_path))
        except StoreError as exc:
            raise HistoryChainMismatch(
                "legacy conceptric history is not canonical JSONL", path=str(self.legacy_path)
            ) from exc
        return self._verify_rows(tuple(StoredEvent.from_dict(raw) for raw in raw_rows))

    @staticmethod
    def _verify_rows(rows: tuple[StoredEvent, ...]) -> tuple[StoredEvent, ...]:
        previous = GENESIS_DIGEST
        for expected_sequence, row in enumerate(rows, start=1):
            if row.sequence != expected_sequence or row.previous_digest != previous:
                raise HistoryChainMismatch(
                    "history sequence or predecessor does not verify",
                    expected_sequence=expected_sequence,
                    got_sequence=row.sequence,
                    expected_previous=previous,
                    got_previous=row.previous_digest,
                )
            previous = row.record_digest
        return rows

    @staticmethod
    def _insert_event_v1(connection: sqlite3.Connection, stored: StoredEvent) -> None:
        event = stored.event
        connection.execute(
            """
            INSERT INTO events(
                sequence, previous_digest, record_digest, event_id, event_kind,
                assumption, fibre, event_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored.sequence,
                stored.previous_digest,
                stored.record_digest,
                event.event_id,
                event.kind.value,
                event.assumption,
                event.fibre,
                canonical_json(event.to_dict()),
            ),
        )

    @staticmethod
    def _insert_event_v2(
        connection: sqlite3.Connection, stored: StoredEvent, event_handle: str
    ) -> None:
        event = stored.event
        connection.execute(
            """
            INSERT INTO events(
                sequence, previous_digest, record_digest, event_id, event_kind,
                assumption, fibre, event_handle
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored.sequence,
                stored.previous_digest,
                stored.record_digest,
                event.event_id,
                event.kind.value,
                event.assumption,
                event.fibre,
                event_handle,
            ),
        )

    @staticmethod
    def _project_delta(
        connection: sqlite3.Connection,
        before: ConceptricState,
        after: ConceptricState,
        event_id: str,
    ) -> None:
        for object_id in after.graph_objects.keys() - before.graph_objects.keys():
            item = after.graph_objects[object_id]
            connection.execute(
                """
                INSERT INTO objects(
                    object_id, kind, content_handle, assumption, fibre,
                    grade_contract_id, grade_coordinate_json, declared_event_id, object_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.object_id,
                    item.kind,
                    item.content_handle,
                    item.assumption,
                    item.fibre,
                    item.grade_contract_id,
                    canonical_json(item.grade_coordinate),
                    event_id,
                    canonical_json(item.to_dict()),
                ),
            )

        # The event ledger accumulates; these rows do not.  Each changed message advances one
        # commission's live review frontier in place.  Exact commission evidence remains in the
        # ledger and hives, while wake can later read every unresolved row plus a bounded terminal
        # tail without replaying or serialising the message history.
        changed_messages = {
            message_id
            for message_id, record in after.messages.items()
            if before.messages.get(message_id) != record
        }
        for message_id in sorted(
            changed_messages,
            key=lambda item: after.messages[item].message.cursor,
        ):
            ConceptricStore._project_seat_mail_record(
                connection,
                after.messages[message_id],
                event_id=event_id,
                event_cursor=after.event_count,
            )
            ConceptricStore._project_review_record(connection, after.messages[message_id])

        for seat_id in before.seat_occupancies.keys() - after.seat_occupancies.keys():
            connection.execute(
                "DELETE FROM provider_session_seat_projection WHERE seat_id = ?",
                (seat_id,),
            )
            connection.execute(
                "DELETE FROM seat_occupancy_projection WHERE seat_id = ?",
                (seat_id,),
            )
        for seat_id, occupancy in after.seat_occupancies.items():
            if before.seat_occupancies.get(seat_id) == occupancy:
                continue
            connection.execute(
                "DELETE FROM provider_session_seat_projection WHERE seat_id = ?",
                (seat_id,),
            )
            connection.execute(
                """
                INSERT INTO seat_occupancy_projection(seat_id, occupancy_json)
                VALUES (?, ?)
                ON CONFLICT(seat_id) DO UPDATE SET
                    occupancy_json = excluded.occupancy_json
                """,
                (seat_id, canonical_json(occupancy.to_dict())),
            )
            if occupancy.routing_authority and occupancy.binding is not None:
                connection.execute(
                    """
                    INSERT INTO provider_session_seat_projection(
                        provider_session_ref, seat_id, occupancy_json
                    ) VALUES (?, ?, ?)
                    """,
                    (
                        occupancy.binding.provider_session_ref,
                        seat_id,
                        canonical_json(occupancy.to_dict()),
                    ),
                )
        for lease_id, lease in after.region_leases.items():
            if before.region_leases.get(lease_id) == lease:
                continue
            connection.execute(
                """
                INSERT INTO region_lease_projection(lease_id, lease_json)
                VALUES (?, ?)
                ON CONFLICT(lease_id) DO UPDATE SET lease_json = excluded.lease_json
                """,
                (lease_id, canonical_json(lease.to_dict())),
            )

        connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('active_assumption', ?)",
            (after.active_assumption or "",),
        )
        connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('active_fibre', ?)",
            (after.active_fibre or "",),
        )
        connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('projected_event_count', ?)",
            (str(after.event_count),),
        )
        connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('projected_head_event_id', ?)",
            (after.head_event_id or "",),
        )
        for edge_id in after.graph_edges.keys() - before.graph_edges.keys():
            edge = after.graph_edges[edge_id]
            connection.execute(
                """
                INSERT INTO edges(
                    edge_id, relation, source_object_id, target_object_id, direction,
                    assumption, fibre, operator, generation_handle, declared_event_id, edge_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge.edge_id,
                    edge.relation,
                    edge.source_object_id,
                    edge.target_object_id,
                    edge.direction.value,
                    edge.assumption,
                    edge.fibre,
                    edge.operator,
                    edge.generation_handle,
                    event_id,
                    canonical_json(edge.to_dict()),
                ),
            )

    def _retire_legacy_receipt(self, digest: str) -> None:
        if not self.legacy_path.exists():
            return
        if self.legacy_receipt_path.exists():
            if sha256_file(self.legacy_receipt_path) != digest:
                raise StoreError(
                    "legacy receipt path already contains different bytes",
                    path=str(self.legacy_receipt_path),
                )
            self.legacy_path.unlink()
            return
        os.replace(self.legacy_path, self.legacy_receipt_path)

    def _import_legacy_v1(
        self, connection: sqlite3.Connection, rows: tuple[StoredEvent, ...], digest: str
    ) -> None:
        state = ConceptricState()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for stored in rows:
                next_state = apply_event(state, stored.event)
                self._insert_event_v1(connection, stored)
                self._project_delta(connection, state, next_state, stored.event.event_id)
                state = next_state
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('legacy_jsonl_sha256', ?)",
                (digest,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('graph_projection_schema', ?)",
                (LEGACY_GRAPH_PROJECTION_SCHEMA,),
            )
            connection.commit()
        except (sqlite3.Error, AtlasError):
            connection.rollback()
            raise

    def _import_legacy_v2(
        self, connection: sqlite3.Connection, rows: tuple[StoredEvent, ...], digest: str
    ) -> None:
        handles = [self.hive.put(canonical_json(row.event.to_dict()).encode()) for row in rows]
        try:
            connection.execute("BEGIN IMMEDIATE")
            for stored, handle in zip(rows, handles, strict=True):
                self._insert_event_v2(connection, stored, handle)
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('legacy_jsonl_sha256', ?)",
                (digest,),
            )
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            raise

    def _read_v1_rows_from(self, connection: sqlite3.Connection) -> tuple[StoredEvent, ...]:
        rows: list[StoredEvent] = []
        for raw in connection.execute(
            "SELECT sequence, previous_digest, record_digest, event_json "
            "FROM events ORDER BY sequence"
        ):
            try:
                event_raw = json.loads(raw["event_json"])
            except ValueError as exc:
                raise HistoryChainMismatch(
                    "database event envelope is not valid canonical JSON",
                    sequence=raw["sequence"],
                ) from exc
            rows.append(self._stored_from_raw(raw, event_raw))
        return self._verify_rows(tuple(rows))

    def _stored_v2_from_raw(self, raw: sqlite3.Row) -> StoredEvent:
        data = self.hive.get(raw["event_handle"])
        try:
            event_raw = json.loads(data)
        except (TypeError, ValueError) as exc:
            raise HistoryChainMismatch(
                "hived event envelope is not valid JSON", sequence=raw["sequence"]
            ) from exc
        if canonical_json(event_raw).encode() != data:
            raise HistoryChainMismatch(
                "hived event envelope is not canonical JSON", sequence=raw["sequence"]
            )
        stored = self._stored_from_raw(raw, event_raw)
        event = stored.event
        compact = (event.event_id, event.kind.value, event.assumption, event.fibre)
        indexed = (raw["event_id"], raw["event_kind"], raw["assumption"], raw["fibre"])
        if compact != indexed:
            raise HistoryChainMismatch(
                "compact ledger facts disagree with hived event", sequence=raw["sequence"]
            )
        return stored

    @classmethod
    def _cached_verified_tip(
        cls,
        raw: sqlite3.Row,
        hive: CompressedHive,
    ) -> tuple[StoredEvent, bool]:
        """Verify a compact tip, inflating its CAS envelope once per process coordinate."""

        key = (int(raw["sequence"]), str(raw["record_digest"]))
        event_handle = str(raw["event_handle"])
        event_path = hive.key_path(event_handle)
        with _AUTHORITY_TIP_CACHE_LOCK:
            cached = _AUTHORITY_TIP_CACHE.get(key)
            if cached is not None:
                cached_handle, stored, cached_path, cached_stat = cached
                try:
                    current_stat = event_path.stat()
                    current_signature = (current_stat.st_size, current_stat.st_mtime_ns)
                except OSError:
                    current_signature = (-1, -1)
                if cached_path != event_path or cached_stat != current_signature:
                    cached = None
                    _AUTHORITY_TIP_CACHE.pop(key, None)
            if cached is not None:
                cached_handle, stored, _cached_path, _cached_stat = cached
                event = stored.event
                compact = (
                    stored.sequence,
                    stored.previous_digest,
                    stored.record_digest,
                    event.event_id,
                    event.kind.value,
                    event.assumption,
                    event.fibre,
                    cached_handle,
                )
                indexed = (
                    int(raw["sequence"]),
                    str(raw["previous_digest"]),
                    str(raw["record_digest"]),
                    str(raw["event_id"]),
                    str(raw["event_kind"]),
                    raw["assumption"],
                    raw["fibre"],
                    event_handle,
                )
                if compact != indexed:
                    raise HistoryChainMismatch(
                        "cached authority tip disagrees with compact ledger facts",
                        sequence=raw["sequence"],
                    )
                return stored, True

            face = object.__new__(cls)
            face.hive = hive
            stored = face._stored_v2_from_raw(raw)
            verified_stat = event_path.stat()
            verified_signature = (verified_stat.st_size, verified_stat.st_mtime_ns)
            if len(_AUTHORITY_TIP_CACHE) >= _AUTHORITY_TIP_CACHE_LIMIT:
                _AUTHORITY_TIP_CACHE.pop(next(iter(_AUTHORITY_TIP_CACHE)))
            _AUTHORITY_TIP_CACHE[key] = (
                event_handle,
                stored,
                event_path,
                verified_signature,
            )
            return stored, False

    def _read_v2_rows_from(self, connection: sqlite3.Connection) -> tuple[StoredEvent, ...]:
        rows: list[StoredEvent] = []
        for raw in connection.execute(
            "SELECT sequence, previous_digest, record_digest, event_id, event_kind, "
            "assumption, fibre, event_handle FROM events ORDER BY sequence"
        ):
            rows.append(self._stored_v2_from_raw(raw))
        return self._verify_rows(tuple(rows))

    def _read_v2_suffix_from(
        self,
        connection: sqlite3.Connection,
        *,
        after_sequence: int,
        previous_digest: str,
    ) -> tuple[StoredEvent, ...]:
        """Verify only the causal suffix after an already verified in-process head."""

        rows: list[StoredEvent] = []
        expected_sequence = after_sequence + 1
        expected_previous = previous_digest
        for raw in connection.execute(
            "SELECT sequence, previous_digest, record_digest, event_id, event_kind, "
            "assumption, fibre, event_handle FROM events WHERE sequence > ? "
            "ORDER BY sequence",
            (after_sequence,),
        ):
            stored = self._stored_v2_from_raw(raw)
            if stored.sequence != expected_sequence or stored.previous_digest != expected_previous:
                raise HistoryChainMismatch(
                    "history suffix does not join the verified in-process head",
                    expected_sequence=expected_sequence,
                    got_sequence=stored.sequence,
                    expected_previous=expected_previous,
                    got_previous=stored.previous_digest,
                )
            rows.append(stored)
            expected_sequence += 1
            expected_previous = stored.record_digest
        return tuple(rows)

    @staticmethod
    def _stored_from_raw(raw: sqlite3.Row, event_raw: dict[str, Any]) -> StoredEvent:
        return StoredEvent.from_dict(
            {
                "schema_version": HISTORY_ROW_SCHEMA,
                "sequence": raw["sequence"],
                "previous_digest": raw["previous_digest"],
                "record_digest": raw["record_digest"],
                "event": event_raw,
            }
        )

    def _read_rows_from(self, connection: sqlite3.Connection) -> tuple[StoredEvent, ...]:
        if self.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA:
            return self._read_v1_rows_from(connection)
        return self._read_v2_rows_from(connection)

    def _projection_connection_for_replay(self) -> sqlite3.Connection:
        if self.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA:
            return self._connect()
        return self._connect_projection()

    @staticmethod
    def _head_digest(rows: tuple[StoredEvent, ...]) -> str:
        return GENESIS_DIGEST if not rows else rows[-1].record_digest

    def _rebuild_graph_projection(
        self,
        connection: sqlite3.Connection,
        rows: tuple[StoredEvent, ...],
        *,
        projection_schema: str | None = None,
    ) -> None:
        self._create_projection_schema(connection)
        projection_schema = projection_schema or (
            LEGACY_GRAPH_PROJECTION_SCHEMA
            if self.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA
            else GRAPH_PROJECTION_SCHEMA
        )
        state = ConceptricState()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM edges")
            connection.execute("DELETE FROM objects")
            connection.execute("DELETE FROM development_reviews")
            connection.execute("DELETE FROM development_review_counts")
            connection.execute("DELETE FROM seat_occupancy_projection")
            connection.execute("DELETE FROM provider_session_seat_projection")
            connection.execute("DELETE FROM region_lease_projection")
            connection.execute("DELETE FROM seat_mail_pending")
            connection.execute("DELETE FROM seat_mail_frontiers")
            for stored in rows:
                next_state = apply_event(state, stored.event)
                self._project_delta(connection, state, next_state, stored.event.event_id)
                state = next_state
            for key, value in (
                ("active_assumption", state.active_assumption or ""),
                ("active_fibre", state.active_fibre or ""),
                ("projected_event_count", str(state.event_count)),
                ("projected_head_event_id", state.head_event_id or ""),
            ):
                connection.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                    (key, value),
                )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('graph_projection_schema', ?)",
                (projection_schema,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES "
                "('development_review_projection_schema', ?)",
                (DEVELOPMENT_REVIEW_PROJECTION_SCHEMA,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('seat_mail_projection_schema', ?)",
                (SEAT_MAIL_PROJECTION_SCHEMA,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('authoritative_head_digest', ?)",
                (self._head_digest(rows),),
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES "
                "('development_review_head_digest', ?)",
                (self._head_digest(rows),),
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('seat_mail_head_digest', ?)",
                (self._head_digest(rows),),
            )
            connection.commit()
        except (sqlite3.Error, AtlasError):
            connection.rollback()
            raise

    def _replace_graph_projection(
        self,
        rows: tuple[StoredEvent, ...],
        *,
        projection_schema: str = GRAPH_PROJECTION_SCHEMA,
    ) -> None:
        """Atomically replace the derived graph cache from verified authority.

        A projection is disposable only if every writable face can recover from arbitrary
        cache bytes without asking a human to delete them.  Build beside the incumbent first;
        the ledger and hives are never touched, and the replacement becomes visible in one
        rename while the caller owns the exclusive store lock.
        """

        candidate = self._temporary_database(self.root, "conceptric-index-rebuild")
        try:
            with self._open_sqlite(candidate, wal=False) as projection:
                self._rebuild_graph_projection(
                    projection, rows, projection_schema=projection_schema
                )
                self._verify_graph_projection(projection, self._fold(rows), rows)
            for suffix in ("-wal", "-shm"):
                sidecar = self.projection_path.with_name(self.projection_path.name + suffix)
                self._discard_disposable_file_or_quarantine(sidecar)
            # Replacing an ordinary cache inode is itself the atomic retirement.  Keeping every
            # prior 80 MB projection as forensic evidence made storage grow with the number of
            # schema/crash repairs even though canonical Atlas could reconstruct every byte.
            # Preserve only genuinely anomalous path shapes; a regular file or symlink is safely
            # replaced at the directory-entry boundary below.
            if (
                os.path.lexists(self.projection_path)
                and self.projection_path.is_dir()
                and not self.projection_path.is_symlink()
            ):
                self._retire_disposable_obstruction(self.projection_path)
            os.replace(candidate, self.projection_path)
            candidate = None
            self._fsync_directory(self.root)
        finally:
            if candidate is not None and candidate.exists():
                candidate.unlink()

    def _discard_disposable_file_or_quarantine(self, path: Path) -> Path | None:
        """Bound cache retirement while preserving an anomalous filesystem plant.

        Ordinary SQLite sidecars are derived bytes and may be unlinked under the exclusive store
        lock.  A directory at a sidecar path is not a SQLite generation; quarantine it rather
        than recursively deleting unknown contents.
        """

        if not os.path.lexists(path):
            return None
        if path.is_dir() and not path.is_symlink():
            return self._retire_disposable_obstruction(path)
        try:
            path.unlink()
        except OSError as exc:
            raise StoreError(
                "disposable projection sidecar could not be retired",
                path=str(path),
            ) from exc
        return None

    def _retire_disposable_obstruction(self, path: Path) -> Path | None:
        """Move arbitrary cache-path poison aside without deleting its evidence.

        A file, directory or symlink at a disposable projection path has no authority, but an
        unexpected directory must not permanently brick every writer and must not be recursively
        deleted on trust.  Rename it atomically to a unique hidden residue under the same root;
        the clean cache can then take the canonical path and the planted bytes remain inspectable.
        """

        if not os.path.lexists(path):
            return None
        residue = path.with_name(f".{path.name}.retired-{uuid.uuid4().hex}")
        try:
            os.replace(path, residue)
        except OSError as exc:
            raise StoreError(
                "disposable projection obstruction could not be quarantined",
                path=str(path),
                residue=str(residue),
            ) from exc
        return residue

    def _ensure_projection(self, rows: tuple[StoredEvent, ...]) -> None:
        expected_schema = (
            LEGACY_GRAPH_PROJECTION_SCHEMA
            if self.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA
            else GRAPH_PROJECTION_SCHEMA
        )
        if self.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA:
            with self._projection_connection_for_replay() as projection:
                self._create_projection_schema(projection)
                projection.commit()
                schema = projection.execute(
                    "SELECT value FROM meta WHERE key = 'graph_projection_schema'"
                ).fetchone()
                if schema is None or schema["value"] != expected_schema:
                    self._rebuild_graph_projection(
                        projection, rows, projection_schema=expected_schema
                    )
            return

        try:
            if not self.projection_path.is_file():
                raise StoreError(
                    "disposable graph projection is absent", path=str(self.projection_path)
                )
            with self._open_sqlite(self.projection_path, read_only=True) as projection:
                schema = projection.execute(
                    "SELECT value FROM meta WHERE key = 'graph_projection_schema'"
                ).fetchone()
                head = projection.execute(
                    "SELECT value FROM meta WHERE key = 'authoritative_head_digest'"
                ).fetchone()
                review_schema = projection.execute(
                    "SELECT value FROM meta WHERE key = 'development_review_projection_schema'"
                ).fetchone()
                review_head = projection.execute(
                    "SELECT value FROM meta WHERE key = 'development_review_head_digest'"
                ).fetchone()
                mail_schema = projection.execute(
                    "SELECT value FROM meta WHERE key = 'seat_mail_projection_schema'"
                ).fetchone()
                mail_head = projection.execute(
                    "SELECT value FROM meta WHERE key = 'seat_mail_head_digest'"
                ).fetchone()
                expected_head = self._head_digest(rows)
                if (
                    schema is None
                    or schema["value"] != expected_schema
                    or head is None
                    or head["value"] != expected_head
                    or review_schema is None
                    or review_schema["value"] != DEVELOPMENT_REVIEW_PROJECTION_SCHEMA
                    or review_head is None
                    or review_head["value"] != expected_head
                    or mail_schema is None
                    or mail_schema["value"] != SEAT_MAIL_PROJECTION_SCHEMA
                    or mail_head is None
                    or mail_head["value"] != expected_head
                ):
                    raise HistoryChainMismatch(
                        "disposable graph projection is stale",
                        expected_schema=expected_schema,
                        expected_head=expected_head,
                    )
                self._verify_graph_projection(projection, self._fold(rows), rows)
                return
        except (AtlasError, sqlite3.Error):
            self._replace_graph_projection(rows, projection_schema=expected_schema)

    def _ensure_database(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            schema = self._schema_version(connection)
            new_store = schema is None
            if schema is None:
                existing = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                if existing:
                    raise StoreError(
                        "conceptric database has tables but no declared schema",
                        tables=[row["name"] for row in existing],
                    )
                hive_root = self._requested_hive_root or (self.root / DEFAULT_EVENT_HIVE_REF)
                hive_ref = self._hive_ref(self.root, hive_root)
                self._create_v2_schema(connection, hive_ref=hive_ref)
                connection.commit()
                schema = CONCEPTRIC_DB_SCHEMA
            if schema not in (LEGACY_CONCEPTRIC_DB_SCHEMA, CONCEPTRIC_DB_SCHEMA):
                raise StoreError(
                    "conceptric database schema is unknown",
                    expected=[LEGACY_CONCEPTRIC_DB_SCHEMA, CONCEPTRIC_DB_SCHEMA],
                    got=schema,
                )
            self.schema_version = schema
            if schema == CONCEPTRIC_DB_SCHEMA:
                self._configure_hive(connection)
                if self._expected_store_role is not None:
                    expected_identity = {
                        "schema_version": "atlas.store-identity/1",
                        "role": self._expected_store_role,
                        "database_ref": self.path.name,
                    }
                    identity_row = connection.execute(
                        "SELECT value FROM meta WHERE key = 'store_identity_json'"
                    ).fetchone()
                    anchor_row = connection.execute(
                        "SELECT value FROM meta WHERE key = 'store_role_anchor_json'"
                    ).fetchone()
                    for operation, row in (
                        ("writable store identity", identity_row),
                        ("writable store role anchor", anchor_row),
                    ):
                        if row is None:
                            continue
                        try:
                            recorded = json.loads(str(row["value"]))
                        except ValueError as exc:
                            raise StoreError(f"{operation} is malformed") from exc
                        self._validate_store_identity(recorded, operation=operation)
                    if anchor_row is None and identity_row is None:
                        connection.execute(
                            "INSERT INTO meta(key, value) VALUES ('store_role_anchor_json', ?)",
                            (canonical_json(expected_identity),),
                        )
            elif self._requested_hive_root is not None:
                raise StoreError(
                    "a legacy store must be migrated before selecting an event hive",
                    path=str(self.path),
                )
            event_count = connection.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
            if self.legacy_path.exists():
                digest = sha256_file(self.legacy_path)
                recorded = connection.execute(
                    "SELECT value FROM meta WHERE key = 'legacy_jsonl_sha256'"
                ).fetchone()
                if event_count == 0:
                    rows = self._legacy_rows()
                    if schema == CONCEPTRIC_DB_SCHEMA:
                        self._import_legacy_v2(connection, rows, digest)
                    else:
                        self._import_legacy_v1(connection, rows, digest)
                elif recorded is None or recorded["value"] != digest:
                    raise StoreError(
                        "legacy JSONL changed or appeared after SQLite migration",
                        path=str(self.legacy_path),
                    )
                self._retire_legacy_receipt(digest)
            connection.commit()
            rows = self._read_rows_from(connection)
            if self.schema_version == CONCEPTRIC_DB_SCHEMA:
                verified_head = self._head_digest(rows)
                recorded_head = connection.execute(
                    "SELECT value FROM meta WHERE key = 'authoritative_head_digest'"
                ).fetchone()
                if recorded_head is not None and recorded_head["value"] not in {
                    GENESIS_DIGEST,
                    verified_head,
                }:
                    raise HistoryChainMismatch(
                        "compact ledger head receipt disagrees with verified history",
                        recorded=recorded_head["value"],
                        verified=verified_head,
                    )
                # Older v2 candidates wrote this receipt only into the disposable index.
                # Reconstruction is the one legitimate place to backfill it into authority.
                connection.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES "
                    "('authoritative_head_digest', ?)",
                    (verified_head,),
                )
                connection.commit()
            self._prime_verified_head(rows)
            if self.schema_version == CONCEPTRIC_DB_SCHEMA and new_store:
                checkpoint = self._checkpoint_for_state(
                    self._verified_state,
                    head_record_digest=self._verified_head_digest,
                )
                self._write_checkpoint(connection, checkpoint)
                connection.commit()
        self._ensure_projection(rows)

    def _read_rows(self) -> tuple[StoredEvent, ...]:
        with self._connect() as connection:
            self._refresh_schema(connection)
            return self._read_rows_from(connection)

    @staticmethod
    def _fold(rows: tuple[StoredEvent, ...]) -> ConceptricState:
        state = ConceptricState()
        for row in rows:
            state = apply_event(state, row.event)
        return state

    def _prime_verified_head(self, rows: tuple[StoredEvent, ...]) -> None:
        """Cache one fully verified replay for O(delta) appends on this store instance."""

        state = self._fold(rows)
        sequence = len(rows)
        head_digest = self._head_digest(rows)
        with self._verified_cache_lock:
            self._verified_state = state
            self._verified_sequence = sequence
            self._verified_head_digest = head_digest

    @staticmethod
    def _compact_tip(connection: sqlite3.Connection) -> tuple[int, str]:
        row = connection.execute(
            "SELECT sequence, record_digest FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return 0, GENESIS_DIGEST
        return int(row["sequence"]), str(row["record_digest"])

    @classmethod
    def read_drift_token(cls, root: Path, *, immutable: bool = False) -> dict[str, Any]:
        """Read the causal ledger tip without constructing or replaying the store.

        This token invalidates a previously verified projection; it is not itself a history
        verification receipt.  Its identity fields exist unchanged in schema v1 and v2, so an
        exact hived migration does not masquerade as semantic movement.  Opening SQLite in
        read-only/query-only mode also keeps a cache probe from creating files or moving WAL state.
        """

        path = Path(root) / "conceptric.sqlite3"
        try:
            connection = sqlite3.connect(
                path.resolve().as_uri() + ("?mode=ro&immutable=1" if immutable else "?mode=ro"),
                uri=True,
                timeout=5.0,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            try:
                schema = cls._schema_version(connection)
                if schema not in (LEGACY_CONCEPTRIC_DB_SCHEMA, CONCEPTRIC_DB_SCHEMA):
                    raise StoreError(
                        "conceptric database schema is unknown",
                        expected=[LEGACY_CONCEPTRIC_DB_SCHEMA, CONCEPTRIC_DB_SCHEMA],
                        got=schema,
                    )
                row = connection.execute(
                    "SELECT sequence, record_digest, event_id "
                    "FROM events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
            finally:
                connection.close()
        except StoreError:
            raise
        except sqlite3.Error as exc:
            raise StoreError(
                "conceptric drift token could not be read",
                path=str(path),
                error=str(exc),
            ) from exc

        return {
            "schema_version": "atlas.conceptric-drift-token/1",
            "cursor": 0 if row is None else int(row["sequence"]),
            "head_event_id": None if row is None else str(row["event_id"]),
            "head_record_digest": GENESIS_DIGEST if row is None else str(row["record_digest"]),
        }

    @classmethod
    def read_authority_checkpoint(
        cls,
        root: Path,
        *,
        expected_context: Mapping[str, str] | None = None,
        extra_authority_files: tuple[Path, ...] = (),
    ) -> dict[str, Any]:
        """Verify one checksummed head-bound authority scaffold without global replay.

        Missing, malformed, stale, moved or context-mismatched checkpoints refuse.  Live readers
        never invoke the deep verifier implicitly; recovery is a stopped-writer operation.
        """

        started_wall = time.perf_counter_ns()
        started_cpu = time.process_time_ns()
        root = Path(root)
        lock_face = object.__new__(cls)
        lock_face.root = root
        lock_face.lock_path = root / "conceptric.lock"
        lock_face.read_only = True
        with lock_face._locked(shared=True), cls._open_sqlite(
            root / "conceptric.sqlite3", read_only=True
        ) as ledger:
            schema = cls._schema_version(ledger)
            store_role = None if expected_context is not None else cls._anchored_store_role(ledger)
            context = cls._normalize_authority_context(
                expected_context,
                root=root,
                store_role=store_role,
                extra_authority_files=extra_authority_files,
            )
            if schema != CONCEPTRIC_DB_SCHEMA:
                return {
                    "schema_version": AUTHORITY_CHECKPOINT_SCHEMA,
                    "status": "NO-CHECKPOINT",
                    "mode": "legacy-deep",
                    "reason": "ledger schema predates canonical authority checkpoints",
                    "read_only": True,
                }
            tip = ledger.execute(
                "SELECT sequence, previous_digest, record_digest, event_id, event_kind, "
                "assumption, fibre, event_handle FROM events "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            cursor = 0 if tip is None else int(tip["sequence"])
            head_digest = GENESIS_DIGEST if tip is None else str(tip["record_digest"])
            head_event_id = None if tip is None else str(tip["event_id"])
            checkpoint_table = ledger.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                "AND name = 'authority_checkpoint'"
            ).fetchone()
            if checkpoint_table is None:
                return {
                    "schema_version": AUTHORITY_CHECKPOINT_SCHEMA,
                    "status": "NO-CHECKPOINT",
                    "mode": "legacy-deep",
                    "reason": "checkpoint table is absent pending explicit writer adoption",
                    "drift_token": {
                        "cursor": cursor,
                        "head_event_id": head_event_id,
                        "head_record_digest": head_digest,
                    },
                    "read_only": True,
                }
            try:
                raw = ledger.execute(
                    "SELECT checkpoint_json, checkpoint_digest "
                    "FROM authority_checkpoint WHERE singleton = 1"
                ).fetchone()
            except sqlite3.Error as exc:
                raise HistoryChainMismatch(
                    "authority checkpoint schema is corrupt or unreadable"
                ) from exc
            if raw is None:
                raise HistoryChainMismatch("authority checkpoint table has no singleton row")
            try:
                body = json.loads(str(raw["checkpoint_json"]))
            except (TypeError, ValueError) as exc:
                raise HistoryChainMismatch("canonical authority checkpoint is malformed") from exc
            if canonical_json(body) != str(raw["checkpoint_json"]):
                raise HistoryChainMismatch("canonical authority checkpoint is not canonical JSON")
            digest = chash(body)
            if digest != str(raw["checkpoint_digest"]):
                raise HistoryChainMismatch("canonical authority checkpoint digest does not verify")
            try:
                checkpoint = AuthorityCheckpoint.from_dict(body)
            except (TypeError, ValueError) as exc:
                raise HistoryChainMismatch("canonical authority checkpoint shape is invalid") from exc
            anchor_checkpoint = checkpoint.to_dict()
            anchor_checkpoint_digest = digest
            if checkpoint.cursor > cursor:
                raise HistoryChainMismatch(
                    "canonical authority checkpoint is stale, moved or forked",
                    checkpoint_cursor=checkpoint.cursor,
                    ledger_cursor=cursor,
                    checkpoint_head=checkpoint.head_record_digest,
                    ledger_head=head_digest,
                )
            hive_ref = ledger.execute(
                "SELECT value FROM meta WHERE key = 'event_hive_ref'"
            ).fetchone()
            if hive_ref is None:
                raise HistoryChainMismatch("canonical authority checkpoint has no event hive")
            hive_path = Path(str(hive_ref["value"]))
            if not hive_path.is_absolute():
                hive_path = root / hive_path
            verifier = object.__new__(cls)
            verifier.hive = CompressedHive(hive_path)
            suffix_rows: tuple[StoredEvent, ...] = ()
            tip_cache_hit = False
            if checkpoint.cursor == cursor:
                if (
                    checkpoint.head_event_id,
                    checkpoint.head_record_digest,
                ) != (head_event_id, head_digest):
                    raise HistoryChainMismatch(
                        "canonical authority checkpoint is stale, moved or forked"
                    )
                if tip is not None:
                    verified_tip, tip_cache_hit = cls._cached_verified_tip(tip, verifier.hive)
                    if (
                        verified_tip.event.event_id,
                        verified_tip.record_digest,
                    ) != (head_event_id, head_digest):
                        raise HistoryChainMismatch(
                            "canonical authority checkpoint tip evidence disagrees"
                        )
            else:
                raw_suffix = tuple(
                    ledger.execute(
                        "SELECT sequence, previous_digest, record_digest, event_id, event_kind, "
                        "assumption, fibre, event_handle FROM events WHERE sequence > ? "
                        "ORDER BY sequence LIMIT ?",
                        (checkpoint.cursor, AUTHORITY_SUFFIX_LIMIT + 1),
                    )
                )
                if len(raw_suffix) > AUTHORITY_SUFFIX_LIMIT:
                    raise HistoryChainMismatch(
                        "canonical authority suffix exceeds the bounded verification window",
                        checkpoint_cursor=checkpoint.cursor,
                        ledger_cursor=cursor,
                        limit=AUTHORITY_SUFFIX_LIMIT,
                    )
                expected_sequence = checkpoint.cursor + 1
                expected_previous = checkpoint.head_record_digest
                verified: list[StoredEvent] = []
                for raw_suffix_row in raw_suffix:
                    if int(raw_suffix_row["sequence"]) == cursor:
                        stored, tip_cache_hit = cls._cached_verified_tip(
                            raw_suffix_row, verifier.hive
                        )
                    else:
                        stored = verifier._stored_v2_from_raw(raw_suffix_row)
                    if (
                        stored.sequence != expected_sequence
                        or stored.previous_digest != expected_previous
                    ):
                        raise HistoryChainMismatch(
                            "canonical authority suffix contains a gap or fork",
                            expected_sequence=expected_sequence,
                            got_sequence=stored.sequence,
                            expected_previous=expected_previous,
                            got_previous=stored.previous_digest,
                        )
                    verified.append(stored)
                    expected_sequence += 1
                    expected_previous = stored.record_digest
                suffix_rows = tuple(verified)
                if not suffix_rows or (
                    suffix_rows[-1].sequence,
                    suffix_rows[-1].event.event_id,
                    suffix_rows[-1].record_digest,
                ) != (cursor, head_event_id, head_digest):
                    raise HistoryChainMismatch(
                        "canonical authority suffix does not reach the ledger tip"
                    )
                affecting = [
                    row.event.kind.value
                    for row in suffix_rows
                    if row.event.kind.value in AUTHORITY_AFFECTING_EVENT_KINDS
                ]
                if affecting:
                    raise HistoryChainMismatch(
                        "canonical authority suffix contains an uncheckpointed authority transition",
                        status="UNKNOWN",
                        event_kinds=affecting,
                    )
                unclassified = [
                    row.event.kind.value
                    for row in suffix_rows
                    if row.event.kind.value not in AUTHORITY_PROVEN_NEUTRAL_EVENT_KINDS
                ]
                if unclassified:
                    raise HistoryChainMismatch(
                        "canonical authority suffix contains an unclassified transition",
                        status="UNKNOWN",
                        event_kinds=unclassified,
                    )
                checkpoint = AuthorityCheckpoint(
                    cursor=cursor,
                    head_event_id=head_event_id,
                    head_record_digest=head_digest,
                    implementation_digest=checkpoint.implementation_digest,
                    environment_root=checkpoint.environment_root,
                    dirty_paths_root=checkpoint.dirty_paths_root,
                    authority=checkpoint.authority,
                )
            disagreements = {
                key: {"expected": context[key], "checkpoint": getattr(checkpoint, key)}
                for key in context
                if context[key] != getattr(checkpoint, key)
            }
            if disagreements:
                raise HistoryChainMismatch(
                    "canonical authority checkpoint context is UNKNOWN",
                    disagreements=disagreements,
                )
        return {
            "schema_version": AUTHORITY_CHECKPOINT_SCHEMA,
            "status": "CURRENT",
            "checkpoint": checkpoint.to_dict(),
            "checkpoint_digest": chash(checkpoint.to_dict()),
            "anchor_checkpoint": anchor_checkpoint,
            "anchor_checkpoint_digest": anchor_checkpoint_digest,
            "effective_checkpoint": checkpoint.to_dict(),
            "effective_checkpoint_digest": chash(checkpoint.to_dict()),
            "read_metrics": {
                "ledger_rows_loaded": 1 + len(suffix_rows),
                "tip_rows_loaded": 1,
                "checkpoint_rows_loaded": 1,
                "checkpoint_bytes": len(str(raw["checkpoint_json"]).encode("utf-8")),
                "tip_cache_hit": tip_cache_hit,
                "suffix_rows_loaded": len(suffix_rows),
                "historical_event_rows_avoided": max(
                    0, cursor - max(1, len(suffix_rows))
                ),
                "authority_tail_events": sum(
                    row.event.kind.value in AUTHORITY_AFFECTING_EVENT_KINDS
                    for row in suffix_rows
                ),
                "authority_tail_limit": AUTHORITY_SUFFIX_LIMIT,
                "global_history_replayed": False,
                "elapsed_ns": time.perf_counter_ns() - started_wall,
                "cpu_ns": time.process_time_ns() - started_cpu,
            },
            "rollback": {
                "status": "CRUTCH",
                "crutch_id": "CR-5639952-HEAD-BOUND-LIVE-AUTHORITY",
                "predicate": "stop all writers, deep replay exact history, compare checkpoint",
            },
            "integrity_boundary": {
                "status": "CHECKSUMMED-CRUTCH",
                "forgeability_residual": (
                    "adjacent checkpoint and digest are forgeable by local writers"
                ),
                "independent_verifier": "verify_authority_checkpoint_deep (writers stopped)",
            },
            "crutch": {
                "crutch_id": "CR-C2A-CHECKSUMMED-LIVE-AUTHORITY-20260828",
                "owner": "Ego/runtime authority lane",
                "covers": (
                    "head-bound seat/mail/region authority reads without full history replay"
                ),
                "dependents": [
                    "provider binding",
                    "startup mail gate",
                    "region lease projection",
                    "Aisthesis as-of authority face",
                    "C3 wake consumer",
                ],
                "residual": (
                    "adjacent JSON+digest is locally forgeable; pending JSON remains unbounded; "
                    "there is no event/CAS post-state anchor; stopped-writer deep verification "
                    "remains required"
                ),
                "retirement": (
                    "event/CAS-bound post-state root, incremental per-recipient/provider/lease "
                    "accumulators, exact fast==deep plants, and C3 latency/zero-fold evidence"
                ),
            },
            "open_residuals": [
                "CR-C2A-CHECKSUMMED-LIVE-AUTHORITY-20260828",
                "CR-C2-CHECKPOINT-EVENT-CAS-ANCHOR",
                "WO-20260827-attention-accumulator-and-polling-retirement",
                "WO-20260827-store-growth-budget-retention-and-reclaim",
                "P0-EXACT-DESCENT-REGION-LEASE-RESOLVER",
            ],
            "read_only": True,
        }

    @classmethod
    def read_atlas_object(
        cls,
        root: Path,
        *,
        reference: str,
        expected_context: Mapping[str, str] | None = None,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        """Read one exact canonical object through the head-bound read capability.

        This read-only capability is deliberately independent of the writer authority checkpoint.
        The compact ledger tip binds the disposable projection generation; a graph object's
        declaring hived event is then verified by handle.  Region leases use their keyed,
        head-bound projection row.  No checkpoint row or authority implementation context is read,
        so source landing and writer re-adoption cannot close by-handle reads.

        The graph sidecar remains a checksummed crutch: for objects synthesized while folding a
        non-OBJECT event, the declaring event is content-address checked and its provenance must
        cover the sidecar row, but that does not authenticate the row's derivation. Re-deriving
        the object would require predecessor graph state. ``sidecar-duplicate-nonleaf``
        remains explicit in the returned fidelity boundary until a canonical object accumulator
        is event-rooted.
        """

        started_wall = time.perf_counter_ns()
        started_cpu = time.process_time_ns()
        # Kept for source compatibility with older callers.  Writer context is intentionally not
        # consulted by this read capability.
        _ = expected_context
        object_id = str(reference).strip()
        if not object_id:
            raise StoreError(
                "exact Atlas object reference is empty",
                code="NOT_FOUND",
            )
        root = Path(root)
        lock_face = object.__new__(cls)
        lock_face.root = root
        lock_face.lock_path = root / "conceptric.lock"
        lock_face.read_only = True
        ledger_path = root / "conceptric.sqlite3"
        projection_path = root / "conceptric.index.sqlite3"
        projection_rows_loaded = 0
        declaration_rows_loaded = 0
        declared_event_id: str | None = None
        declared_event_record_digest: str | None = None
        declared_event_sequence: int | None = None
        projection_schema: str | None = None
        effective_authority: dict[str, Any] | None = None

        with lock_face._locked(shared=True), cls._open_sqlite(
            ledger_path, read_only=True
        ) as ledger:
            if cls._schema_version(ledger) != CONCEPTRIC_DB_SCHEMA:
                raise StoreError(
                    "exact Atlas object requires the hived ledger",
                    code="UNAVAILABLE",
                )
            tip = ledger.execute(
                "SELECT sequence, previous_digest, record_digest, event_id, event_kind, "
                "assumption, fibre, event_handle FROM events "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            observed_tip = (
                0 if tip is None else int(tip["sequence"]),
                None if tip is None else str(tip["event_id"]),
                GENESIS_DIGEST if tip is None else str(tip["record_digest"]),
            )
            expected_tip = observed_tip
            authoritative_head = ledger.execute(
                "SELECT value FROM meta WHERE key = 'authoritative_head_digest'"
            ).fetchone()
            if authoritative_head is None or str(authoritative_head["value"]) != expected_tip[2]:
                raise HistoryChainMismatch(
                    "Atlas object compact ledger head is dirty",
                    code="DIRTY",
                    expected_head=expected_tip[2],
                    metadata_head=(
                        None if authoritative_head is None else str(authoritative_head["value"])
                    ),
                )
            drift_token = {
                "schema_version": "atlas.conceptric-drift-token/1",
                "cursor": expected_tip[0],
                "head_event_id": expected_tip[1],
                "head_record_digest": expected_tip[2],
            }
            read_head_components = {
                "schema_version": "atlas.keyed-read-head/1",
                "drift_token": drift_token,
                "tip_event_handle": None if tip is None else str(tip["event_handle"]),
            }
            read_head_digest = chash(read_head_components)

            if object_id.startswith("region-lease:"):
                try:
                    with cls._open_sqlite(projection_path, read_only=True) as projection:
                        meta = {
                            str(row["key"]): str(row["value"])
                            for row in projection.execute(
                                "SELECT key, value FROM meta WHERE key IN "
                                "('graph_projection_schema', 'authoritative_head_digest', "
                                "'projected_event_count', 'projected_head_event_id')"
                            )
                        }
                        expected_meta = {
                            "graph_projection_schema": GRAPH_PROJECTION_SCHEMA,
                            "authoritative_head_digest": expected_tip[2],
                            "projected_event_count": str(expected_tip[0]),
                            "projected_head_event_id": expected_tip[1] or "",
                        }
                        disagreements = {
                            key: {"expected": expected_value, "got": meta.get(key)}
                            for key, expected_value in expected_meta.items()
                            if meta.get(key) != expected_value
                        }
                        if disagreements:
                            raise HistoryChainMismatch(
                                "Atlas object projection moved or is unavailable",
                                code="MOVED",
                                disagreements=disagreements,
                            )
                        projection_schema = meta["graph_projection_schema"]
                        projected = tuple(
                            projection.execute(
                                "SELECT lease_json FROM region_lease_projection "
                                "WHERE lease_id = ? LIMIT 2",
                                (object_id,),
                            )
                        )
                except (sqlite3.Error, OSError) as exc:
                    raise StoreError(
                        "Atlas region-lease projection is unavailable",
                        code="UNAVAILABLE",
                        reference=object_id,
                    ) from exc
                projection_rows_loaded = len(projected)
                if not projected:
                    raise StoreError(
                        "region lease does not resolve exactly",
                        code="NOT_FOUND",
                        reference=object_id,
                    )
                if len(projected) != 1:
                    raise HistoryChainMismatch(
                        "Atlas region lease is ambiguous in the keyed projection",
                        code="AMBIGUOUS",
                        reference=object_id,
                        rows=len(projected),
                    )
                try:
                    value = json.loads(str(projected[0]["lease_json"]))
                except (TypeError, ValueError) as exc:
                    raise HistoryChainMismatch(
                        "region-lease authority row is unreadable",
                        code="DIRTY",
                        reference=object_id,
                    ) from exc
                if not isinstance(value, dict) or canonical_json(value) != str(
                    projected[0]["lease_json"]
                ):
                    raise HistoryChainMismatch(
                        "region-lease projection row is dirty",
                        code="DIRTY",
                        reference=object_id,
                    )
                reference_kind = "region-lease"
                authority_root_kind = "atlas.keyed-region-lease-proof/1"
                authority_root = chash(
                    {
                        "schema_version": authority_root_kind,
                        "projection_schema": projection_schema,
                        "projection_head": expected_tip[2],
                        "lease": value,
                    }
                )
                effective_authority = effective_region_lease_projection(
                    value,
                    seat_occupancies=None,
                    observed_at=observed_at,
                )
            else:
                try:
                    with cls._open_sqlite(projection_path, read_only=True) as projection:
                        meta = {
                            str(row["key"]): str(row["value"])
                            for row in projection.execute(
                                "SELECT key, value FROM meta WHERE key IN "
                                "('graph_projection_schema', 'authoritative_head_digest', "
                                "'projected_event_count', 'projected_head_event_id')"
                            )
                        }
                        expected_meta = {
                            "graph_projection_schema": GRAPH_PROJECTION_SCHEMA,
                            "authoritative_head_digest": expected_tip[2],
                            "projected_event_count": str(expected_tip[0]),
                            "projected_head_event_id": expected_tip[1] or "",
                        }
                        disagreements = {
                            key: {"expected": expected_value, "got": meta.get(key)}
                            for key, expected_value in expected_meta.items()
                            if meta.get(key) != expected_value
                        }
                        if disagreements:
                            raise HistoryChainMismatch(
                                "Atlas object projection moved or is unavailable",
                                code="MOVED",
                                disagreements=disagreements,
                            )
                        projection_schema = meta["graph_projection_schema"]
                        projected = tuple(
                            projection.execute(
                                "SELECT object_id, kind, content_handle, assumption, fibre, "
                                "grade_contract_id, grade_coordinate_json, declared_event_id, "
                                "object_json FROM objects WHERE object_id = ? LIMIT 2",
                                (object_id,),
                            )
                        )
                except (sqlite3.Error, OSError) as exc:
                    raise StoreError(
                        "Atlas object projection is unavailable",
                        code="UNAVAILABLE",
                        reference=object_id,
                    ) from exc
                projection_rows_loaded = len(projected)
                if not projected:
                    raise StoreError(
                        "Atlas graph object does not resolve exactly",
                        code="NOT_FOUND",
                        reference=object_id,
                    )
                if len(projected) != 1:
                    raise HistoryChainMismatch(
                        "Atlas graph object is ambiguous in the keyed projection",
                        code="AMBIGUOUS",
                        reference=object_id,
                        rows=len(projected),
                    )
                projected_row = projected[0]
                try:
                    value = json.loads(str(projected_row["object_json"]))
                    item = ConceptricObject.from_dict(value)
                    grade_coordinate = json.loads(str(projected_row["grade_coordinate_json"]))
                except (AtlasError, TypeError, ValueError) as exc:
                    raise HistoryChainMismatch(
                        "Atlas graph object projection row is unreadable",
                        code="DIRTY",
                        reference=object_id,
                    ) from exc
                column_facts = (
                    projected_row["object_id"],
                    projected_row["kind"],
                    projected_row["content_handle"],
                    projected_row["assumption"],
                    projected_row["fibre"],
                    projected_row["grade_contract_id"],
                    grade_coordinate,
                )
                object_facts = (
                    item.object_id,
                    item.kind,
                    item.content_handle,
                    item.assumption,
                    item.fibre,
                    item.grade_contract_id,
                    item.grade_coordinate,
                )
                if (
                    canonical_json(value) != str(projected_row["object_json"])
                    or column_facts != object_facts
                    or item.object_id != object_id
                ):
                    raise HistoryChainMismatch(
                        "Atlas graph object projection row is dirty",
                        code="DIRTY",
                        reference=object_id,
                    )
                declared_event_id = str(projected_row["declared_event_id"])
                raw_event = ledger.execute(
                    "SELECT sequence, previous_digest, record_digest, event_id, event_kind, "
                    "assumption, fibre, event_handle FROM events WHERE event_id = ?",
                    (declared_event_id,),
                ).fetchone()
                declaration_rows_loaded = 0 if raw_event is None else 1
                if raw_event is None:
                    raise HistoryChainMismatch(
                        "Atlas graph object cites an absent declaring event",
                        code="DIRTY",
                        reference=object_id,
                        declared_event_id=declared_event_id,
                    )
                hive_ref = ledger.execute(
                    "SELECT value FROM meta WHERE key = 'event_hive_ref'"
                ).fetchone()
                if hive_ref is None:
                    raise StoreError(
                        "Atlas graph object declaration hive is unavailable",
                        code="UNAVAILABLE",
                    )
                hive_path = Path(str(hive_ref["value"]))
                if not hive_path.is_absolute():
                    hive_path = root / hive_path
                face = object.__new__(cls)
                face.hive = CompressedHive(hive_path)
                declared = face._stored_v2_from_raw(raw_event)
                declared_event_record_digest = declared.record_digest
                declared_event_sequence = declared.sequence
                event_provenance = {
                    canonical_json(source.to_dict()) for source in declared.event.provenance
                }
                object_provenance = {
                    canonical_json(source.to_dict()) for source in item.provenance
                }
                if not object_provenance.issubset(event_provenance):
                    raise HistoryChainMismatch(
                        "Atlas graph object provenance contradicts its declaring event",
                        code="DIRTY",
                        reference=object_id,
                    )
                if declared.event.kind == EventKind.OBJECT and declared.event.payload != value:
                    raise HistoryChainMismatch(
                        "declared Atlas object contradicts its hived event payload",
                        code="DIRTY",
                        reference=object_id,
                    )
                value = item.to_dict()
                reference_kind = "graph-object"
                authority_root_kind = "atlas.keyed-graph-object-proof/1"
                authority_root = chash(
                    {
                        "schema_version": authority_root_kind,
                        "projection_schema": projection_schema,
                        "projection_head": expected_tip[2],
                        "object": value,
                        "declared_event_id": declared_event_id,
                        "declared_event_record_digest": declared_event_record_digest,
                    }
                )

        content = canonical_json(value)
        content_handle = hash_bytes(content.encode("utf-8"))
        suffix_count = 0
        suffix_limit = AUTHORITY_SUFFIX_LIMIT
        current_root_components = {
            "schema_version": "atlas.atlas-object-current-root/1",
            "integrity_boundary": "CHECKSUMMED-CRUTCH",
            "authenticated": False,
            "reference": object_id,
            "reference_kind": reference_kind,
            "content_handle": content_handle,
            "read_head_digest": read_head_digest,
            "authority_root_kind": authority_root_kind,
            "authority_root": authority_root,
            "drift_token": drift_token,
        }
        current_root = chash(current_root_components)
        return {
            "schema_version": "atlas.atlas-object-read/1",
            "status": "CURRENT",
            "current": True,
            "clean": True,
            "authenticated": False,
            "integrity_boundary": "CHECKSUMMED-CRUTCH",
            "authority_suffix_count": suffix_count,
            "authority_suffix_limit": suffix_limit,
            "reference": object_id,
            "reference_kind": reference_kind,
            "value": value,
            "content": content,
            "content_handle": content_handle,
            "media_type": "application/json",
            "current_root": current_root,
            "current_root_components": current_root_components,
            "authority_root": authority_root,
            "authority_root_kind": authority_root_kind,
            "effective_authority": effective_authority,
            "drift_token": drift_token,
            "provenance": {
                "store": os.fspath(root),
                "writer_authority_checkpoint_used": False,
                "read_head_digest": read_head_digest,
                "read_head_components": read_head_components,
                "declared_event_id": declared_event_id,
                "declared_event_record_digest": declared_event_record_digest,
                "declared_event_sequence": declared_event_sequence,
            },
            "read_metrics": {
                "ledger_rows_loaded": 1 if tip is not None else 0,
                "tip_rows_loaded": 1 if tip is not None else 0,
                "tip_event_inflated": False,
                "checkpoint_rows_loaded": 0,
                "checkpoint_bytes": 0,
                "suffix_rows_loaded": 0,
                "authority_tail_limit": AUTHORITY_SUFFIX_LIMIT,
                "projection_rows_loaded": projection_rows_loaded,
                "declaration_event_rows_loaded": declaration_rows_loaded,
                "keyed_object_rows_loaded": 1,
                "global_history_replayed": False,
                "elapsed_ns": time.perf_counter_ns() - started_wall,
                "cpu_ns": time.process_time_ns() - started_cpu,
            },
            "fidelity_boundary": {
                "status": "CHECKSUMMED-CRUTCH",
                "crutch_id": "CR-ATLAS-HEAD-BOUND-KEYED-READ",
                "writer_authority_checkpoint": "not-read",
                "sidecar_residual": (
                    None
                    if reference_kind == "region-lease"
                    else "sidecar-duplicate-nonleaf"
                ),
                "graph_content_claim": (
                    None
                    if reference_kind == "region-lease"
                    else "not event-authenticated; head-bound sidecar row with exact provenance checks"
                ),
                "retirement": (
                    "event/CAS-bound canonical keyed object accumulator and root; "
                    "region-lease lineage proof independent of writer checkpoints"
                ),
            },
            "read_only": True,
            "transition_claim": "none",
            "authority_write": "none",
        }

    @classmethod
    def verify_atlas_object_current_root(
        cls,
        root: Path,
        *,
        reference: str,
        expected_current_root: str,
        expected_context: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Pure just-in-time equality check for one previously reconstructed Atlas object."""

        expected = str(expected_current_root).strip()
        if not expected.startswith(HASH_PREFIX):
            raise StoreError(
                "Atlas object current-root verifier requires a sha256 root",
                code="DIRTY",
            )
        observed = cls.read_atlas_object(
            root,
            reference=reference,
            expected_context=expected_context,
        )
        if observed["current_root"] != expected:
            raise HistoryChainMismatch(
                "Atlas object current root moved",
                code="MOVED",
                reference=reference,
                expected_current_root=expected,
                observed_current_root=observed["current_root"],
                drift_token=observed["drift_token"],
            )
        return {
            "schema_version": "atlas.atlas-object-current-root-verification/1",
            "status": "CURRENT",
            "current": True,
            "clean": True,
            "authenticated": False,
            "integrity_boundary": "CHECKSUMMED-CRUTCH",
            "authority_suffix_count": observed["authority_suffix_count"],
            "authority_suffix_limit": observed["authority_suffix_limit"],
            "reference": str(reference).strip(),
            "current_root": observed["current_root"],
            "authority_root": observed["authority_root"],
            "authority_root_kind": observed["authority_root_kind"],
            "drift_token": observed["drift_token"],
            "read_metrics": observed["read_metrics"],
            "read_only": True,
            "transition_claim": "none",
            "authority_write": "none",
        }

    @classmethod
    def verify_authority_checkpoint_deep(
        cls,
        root: Path,
        *,
        expected_context: Mapping[str, str] | None = None,
        expected_store_role: str | None = None,
        extra_authority_files: tuple[Path, ...] = (),
        immutable: bool = False,
    ) -> dict[str, Any]:
        """Independently reconstruct one stopped-writer candidate and compare the cache."""

        if immutable:
            wal = Path(root) / "conceptric.sqlite3-wal"
            if wal.is_file() and wal.stat().st_size:
                raise StoreError("immutable authority inspection requires a checkpointed WAL")
        store = cls(
            Path(root),
            read_only=True,
            immutable=immutable,
            authority_context=expected_context,
            expected_store_role=expected_store_role,
            extra_authority_files=extra_authority_files,
        )
        with store._locked(shared=True), store._connect() as ledger:
            if immutable:
                store._refuse_uncheckpointed_authority()
            store._refresh_schema(ledger)
            if store.schema_version != CONCEPTRIC_DB_SCHEMA:
                raise StoreError("authority checkpoint deep verification requires hived schema v2")
            rows = store._read_v2_rows_from(ledger)
            state = store._fold(rows)
            head = store._head_digest(rows)
            candidate = store._checkpoint_for_state(state, head_record_digest=head).to_dict()
            candidate_digest = chash(candidate)
            table = ledger.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='authority_checkpoint'"
            ).fetchone()
            if table is None:
                return {
                    "schema_version": "atlas.authority-checkpoint-parity/1",
                    "status": "NO-CHECKPOINT",
                    "mode": "legacy-deep",
                    "verified_predecessor": head,
                    "candidate_checkpoint": candidate,
                    "candidate_checkpoint_digest": candidate_digest,
                    "fast_deep_equal": False,
                    "writer_precondition": "STOPPED",
                }
            raw = ledger.execute(
                "SELECT checkpoint_json, checkpoint_digest FROM authority_checkpoint "
                "WHERE singleton=1"
            ).fetchone()
        if raw is None:
            return {
                "schema_version": "atlas.authority-checkpoint-parity/1",
                "status": "REFUSED",
                "reason": "checkpoint table has no singleton row",
                "verified_predecessor": None,
                "candidate_checkpoint": candidate,
                "candidate_checkpoint_digest": candidate_digest,
                "fast_deep_equal": False,
                "writer_precondition": "STOPPED",
            }
        try:
            body = json.loads(str(raw["checkpoint_json"]))
        except (TypeError, ValueError):
            body = None
        observed_digest = str(raw["checkpoint_digest"])
        if not isinstance(body, Mapping) or canonical_json(body) != str(raw["checkpoint_json"]):
            return {
                "schema_version": "atlas.authority-checkpoint-parity/1",
                "status": "REFUSED",
                "reason": "checkpoint body is malformed or noncanonical",
                "observed_predecessor": observed_digest,
                "verified_predecessor": None,
                "candidate_checkpoint": candidate,
                "candidate_checkpoint_digest": candidate_digest,
                "fast_deep_equal": False,
                "writer_precondition": "STOPPED",
            }
        digest = chash(body)
        if digest != observed_digest:
            return {
                "schema_version": "atlas.authority-checkpoint-parity/1",
                "status": "REFUSED",
                "reason": "checkpoint digest does not verify",
                "observed_predecessor": observed_digest,
                "verified_predecessor": None,
                "candidate_checkpoint": candidate,
                "candidate_checkpoint_digest": candidate_digest,
                "fast_deep_equal": False,
                "writer_precondition": "STOPPED",
            }
        try:
            checkpoint = AuthorityCheckpoint.from_dict(body)
        except (TypeError, ValueError) as exc:
            return {
                "schema_version": "atlas.authority-checkpoint-parity/1",
                "status": "REFUSED",
                "reason": f"checkpoint shape is invalid: {exc}",
                "observed_predecessor": observed_digest,
                "verified_predecessor": None,
                "candidate_checkpoint": candidate,
                "candidate_checkpoint_digest": candidate_digest,
                "fast_deep_equal": False,
                "writer_precondition": "STOPPED",
            }
        if checkpoint.cursor > len(rows):
            prefix_coordinate = None
        elif checkpoint.cursor == 0:
            prefix_coordinate = (None, GENESIS_DIGEST)
        else:
            prefix = rows[checkpoint.cursor - 1]
            prefix_coordinate = (prefix.event.event_id, prefix.record_digest)
        if prefix_coordinate != (checkpoint.head_event_id, checkpoint.head_record_digest):
            return {
                "schema_version": "atlas.authority-checkpoint-parity/1",
                "status": "REFUSED",
                "reason": "authority checkpoint predecessor is not on the ledger prefix",
                "verified_predecessor": None,
                "candidate_checkpoint": candidate,
                "candidate_checkpoint_digest": candidate_digest,
                "fast_deep_equal": False,
                "writer_precondition": "STOPPED",
            }
        disagreements = {
            key: {"candidate": candidate.get(key), "checkpoint": body.get(key)}
            for key in candidate
            if candidate.get(key) != body.get(key)
        }
        context_disagreements = {
            key: value
            for key, value in disagreements.items()
            if key in {"implementation_digest", "environment_root", "dirty_paths_root"}
        }
        exact = not disagreements
        return {
            "schema_version": "atlas.authority-checkpoint-parity/1",
            "status": "EXACT" if exact else "CONTEST",
            "checkpoint": checkpoint.to_dict(),
            "checkpoint_digest": digest,
            "verified_predecessor": digest,
            "candidate_checkpoint": candidate,
            "candidate_checkpoint_digest": candidate_digest,
            "disagreements": disagreements,
            "context_disagreements": context_disagreements,
            "fast_deep_equal": exact,
            "writer_precondition": "STOPPED",
        }

    @classmethod
    def _authoritative_provider_seat_bindings(
        cls,
        root: Path,
        ledger: sqlite3.Connection,
        *,
        provider_session_ref: str,
    ) -> tuple[dict[str, dict[str, Any]], int]:
        """Authenticate a provider route from the bounded seat-lifecycle subchain.

        ``UNBOUND`` cannot be inferred from the absence of a disposable SQL row.  The compact
        ledger indexes event kind, so reconstruct only chair transitions, joins, and occupancy
        bindings, then compare the projection with that authoritative answer.  This is neither a
        provider snapshot nor global state replay; it is the proof for one routing decision.
        """

        hive_ref = ledger.execute("SELECT value FROM meta WHERE key = 'event_hive_ref'").fetchone()
        if hive_ref is None:
            raise StoreError("provider-seat binding has no event hive reference")
        hive_path = Path(str(hive_ref["value"]))
        if not hive_path.is_absolute():
            hive_path = root / hive_path
        face = object.__new__(cls)
        face.hive = CompressedHive(hive_path)
        occupancies: dict[str, SeatOccupancy] = {}
        bindings: dict[str, SeatOccupancyBinding] = {}
        registration_event_ids: dict[str, str] = {}
        retired_binding_generations: dict[str, str] = {}
        cutover_event_id: str | None = None
        rows_loaded = 0
        for raw in ledger.execute(
            "SELECT sequence, previous_digest, record_digest, event_id, event_kind, "
            "assumption, fibre, event_handle FROM events "
            "WHERE event_kind IN "
            "('seat.transition', 'seat.joined', 'seat.occupancy-bound') "
            "ORDER BY sequence"
        ):
            rows_loaded += 1
            stored = face._stored_v2_from_raw(raw)
            event = stored.event
            if event.kind.value == "seat.transition":
                transition = SeatTransition.from_dict(event.payload)
                occupancies.pop(transition.seat_id, None)
                registration_event_ids[transition.seat_id] = event.event_id
                continue
            if event.kind.value == "seat.joined":
                join_schema = event.payload.get("schema_version")
                starts_lifecycle_cutover = (
                    join_schema == SeatJoinReceipt.SCHEMA_VERSION and cutover_event_id is None
                )
                if (
                    join_schema == SeatJoinReceipt.LEGACY_V1_SCHEMA_VERSION
                    and cutover_event_id is not None
                ):
                    raise HistoryChainMismatch(
                        "provider-seat lifecycle subchain contains a legacy join after cutover",
                        cutover_event_id=cutover_event_id,
                        event_id=event.event_id,
                    )
                join = SeatJoinReceipt.from_dict(event.payload)
                predecessor = occupancies.get(join.seat_id)
                pending_predecessor_binding_event_id = None
                retired_binding_event_ids: tuple[str, ...] = ()
                if predecessor is not None and predecessor.routing_authority:
                    legacy_plain_replacement = (
                        event.payload.get("schema_version")
                        == SeatJoinReceipt.LEGACY_V1_SCHEMA_VERSION
                        and predecessor.join.holder_ref != join.holder_ref
                    )
                    if not legacy_plain_replacement:
                        if predecessor.join.function != join.function:
                            raise HistoryChainMismatch(
                                "provider-seat lifecycle handover changes function",
                                seat_id=join.seat_id,
                            )
                        if (
                            event.payload.get("schema_version") != SeatJoinReceipt.SCHEMA_VERSION
                            and predecessor.join.holder_ref != join.holder_ref
                        ):
                            raise HistoryChainMismatch(
                                "provider-seat lifecycle subchain contains an untyped holder replacement",
                                seat_id=join.seat_id,
                                current_holder=predecessor.join.holder_ref,
                                proposed_holder=join.holder_ref,
                            )
                        if (
                            event.payload.get("schema_version") == SeatJoinReceipt.SCHEMA_VERSION
                            and not join.provider_identity_generation
                        ):
                            raise HistoryChainMismatch(
                                "current provider-seat handover omits its successor generation",
                                seat_id=join.seat_id,
                            )
                        expected_predecessor = predecessor.binding_event_id
                        assert expected_predecessor is not None
                        same_seat_binding_causes = {
                            cause
                            for cause in event.causation_ids
                            if cause in bindings and bindings[cause].seat_id == join.seat_id
                        }
                        if same_seat_binding_causes != {expected_predecessor}:
                            raise HistoryChainMismatch(
                                "current provider-seat handover does not name one exact predecessor",
                                seat_id=join.seat_id,
                                expected=expected_predecessor,
                                got=sorted(same_seat_binding_causes),
                            )
                        pending_predecessor_binding_event_id = expected_predecessor
                        retired_binding_event_ids = predecessor.retired_binding_event_ids
                if starts_lifecycle_cutover:
                    occupancies.clear()
                occupancies[join.seat_id] = SeatOccupancy(
                    join=join,
                    join_event_id=event.event_id,
                    joined_at=event.occurred_at,
                    joined_cursor=stored.sequence,
                    pending_predecessor_binding_event_id=(pending_predecessor_binding_event_id),
                    retired_binding_event_ids=retired_binding_event_ids,
                )
                if starts_lifecycle_cutover:
                    cutover_event_id = event.event_id
                continue
            if (
                event.payload.get("schema_version") != SeatOccupancyBinding.SCHEMA_VERSION
                and cutover_event_id is not None
            ):
                raise HistoryChainMismatch(
                    "provider-seat lifecycle subchain contains a legacy binding after cutover",
                    cutover_event_id=cutover_event_id,
                    event_id=event.event_id,
                )
            binding = SeatOccupancyBinding.from_dict(event.payload)
            occupancy = occupancies.get(binding.seat_id)
            if occupancy is None or occupancy.join_event_id != binding.join_event_id:
                raise HistoryChainMismatch(
                    "provider-seat lifecycle subchain does not bind the latest join",
                    seat_id=binding.seat_id,
                    binding_event_id=event.event_id,
                )
            expected_registration = registration_event_ids.get(binding.seat_id)
            if (
                binding.registered_seat_event_id != expected_registration
                or binding.join_event_id not in event.causation_ids
                or expected_registration not in event.causation_ids
            ):
                raise HistoryChainMismatch(
                    "provider-seat lifecycle binding does not carry its current registration and join",
                    seat_id=binding.seat_id,
                    expected_registration_event_id=expected_registration,
                    join_event_id=binding.join_event_id,
                )
            if (
                binding.provider_session_ref != occupancy.join.holder_ref
                or binding.function != occupancy.join.function
            ):
                raise HistoryChainMismatch(
                    "provider-seat lifecycle binding contradicts its latest join",
                    seat_id=binding.seat_id,
                )
            if (
                event.payload.get("schema_version") == SeatOccupancyBinding.SCHEMA_VERSION
                and binding.provider_identity_generation
                != occupancy.join.provider_identity_generation
            ):
                raise HistoryChainMismatch(
                    "provider-seat lifecycle subchain relabels the joined watcher generation",
                    seat_id=binding.seat_id,
                    join_generation=occupancy.join.provider_identity_generation,
                    binding_generation=binding.provider_identity_generation,
                )
            retired_binding_event_ids = occupancy.retired_binding_event_ids
            predecessor_binding_event_id = binding.predecessor_binding_event_id
            if predecessor_binding_event_id is None:
                if occupancy.pending_predecessor_binding_event_id is not None:
                    raise HistoryChainMismatch(
                        "provider-seat lifecycle subchain omits its pending predecessor",
                        seat_id=binding.seat_id,
                    )
            else:
                if predecessor_binding_event_id != occupancy.pending_predecessor_binding_event_id:
                    raise HistoryChainMismatch(
                        "provider-seat lifecycle subchain retires the wrong predecessor",
                        seat_id=binding.seat_id,
                        expected=occupancy.pending_predecessor_binding_event_id,
                        got=predecessor_binding_event_id,
                    )
                retired_binding_event_ids = tuple(
                    dict.fromkeys((*retired_binding_event_ids, predecessor_binding_event_id))
                )
                predecessor_binding = bindings.get(predecessor_binding_event_id)
                if predecessor_binding is None:
                    raise HistoryChainMismatch(
                        "provider-seat lifecycle subchain cannot resolve its predecessor binding",
                        seat_id=binding.seat_id,
                        predecessor_binding_event_id=predecessor_binding_event_id,
                    )
                if (
                    predecessor_binding.seat_id != binding.seat_id
                    or predecessor_binding.registered_principal_ref
                    != binding.registered_principal_ref
                    or predecessor_binding.function != binding.function
                ):
                    raise HistoryChainMismatch(
                        "provider-seat lifecycle subchain predecessor contradicts its successor",
                        seat_id=binding.seat_id,
                    )
                if (
                    predecessor_binding.provider_session_ref != binding.provider_session_ref
                    and event.payload.get("schema_version") != SeatOccupancyBinding.SCHEMA_VERSION
                ):
                    raise HistoryChainMismatch(
                        "legacy provider-seat binding cannot hand over between holders",
                        seat_id=binding.seat_id,
                    )
                if (
                    predecessor_binding.provider_identity_generation is not None
                    and predecessor_binding.provider_identity_generation
                    != binding.retired_provider_identity_generation
                ):
                    raise HistoryChainMismatch(
                        "provider-seat lifecycle subchain retires the wrong generation",
                        seat_id=binding.seat_id,
                    )
                if predecessor_binding_event_id not in event.causation_ids:
                    raise HistoryChainMismatch(
                        "provider-seat lifecycle binding omits its exact predecessor cause",
                        seat_id=binding.seat_id,
                        predecessor_binding_event_id=predecessor_binding_event_id,
                    )
                replayed_retired_bindings = sorted(
                    retired_binding_event_id
                    for retired_binding_event_id in retired_binding_event_ids
                    if retired_binding_generations.get(retired_binding_event_id)
                    == binding.provider_identity_generation
                )
                if replayed_retired_bindings:
                    raise HistoryChainMismatch(
                        "provider-seat lifecycle replays a retired watcher generation",
                        seat_id=binding.seat_id,
                        provider_identity_generation=(binding.provider_identity_generation),
                        retired_binding_event_ids=replayed_retired_bindings,
                    )
                assert binding.retired_provider_identity_generation is not None
                retired_binding_generations[predecessor_binding_event_id] = (
                    binding.retired_provider_identity_generation
                )
            bindings[event.event_id] = binding
            occupancies[binding.seat_id] = SeatOccupancy(
                join=occupancy.join,
                join_event_id=occupancy.join_event_id,
                joined_at=occupancy.joined_at,
                joined_cursor=occupancy.joined_cursor,
                binding=binding,
                binding_event_id=event.event_id,
                bound_at=event.occurred_at,
                pending_predecessor_binding_event_id=None,
                retired_binding_event_ids=retired_binding_event_ids,
            )
        matching = {
            seat_id: occupancy.to_dict()
            for seat_id, occupancy in occupancies.items()
            if occupancy.routing_authority
            and occupancy.binding is not None
            and occupancy.binding.provider_session_ref == provider_session_ref
        }
        return matching, rows_loaded

    @classmethod
    def _read_provider_seat_binding_legacy_deep(
        cls,
        root: Path,
        *,
        provider_session_ref: str,
    ) -> dict[str, Any]:
        """Explicit pre-checkpoint compatibility verifier over complete canonical history."""

        state = cls(Path(root), read_only=True).replay_authority_only()
        matching = {
            seat_id: occupancy.to_dict()
            for seat_id, occupancy in state.seat_occupancies.items()
            if occupancy.routing_authority
            and occupancy.binding is not None
            and occupancy.binding.provider_session_ref == provider_session_ref
        }
        seats = sorted(matching)
        status = "AMBIGUOUS" if len(seats) > 1 else "BOUND" if seats else "UNBOUND"
        seat_id = seats[0] if len(seats) == 1 else None
        return {
            "schema_version": PROVIDER_SEAT_BINDING_FRONTIER_SCHEMA,
            "status": status,
            "provider_session_ref": provider_session_ref,
            "seat_id": seat_id,
            "occupancy": None if seat_id is None else matching[seat_id],
            "matching_seats": seats,
            "read_metrics": {
                "rows_loaded": state.event_count,
                "history_replayed": True,
                "full_state_fallback": True,
            },
            "fidelity_boundary": {
                "status": "LEGACY-DEEP",
                "checkpoint_status": "NO-CHECKPOINT",
                "retirement_trigger": "explicit writer checkpoint adoption",
            },
            "read_only": True,
        }

    @classmethod
    def _read_seat_mail_frontier_legacy_deep(
        cls,
        root: Path,
        *,
        seat_id: str,
        previous_mail_token: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Explicit pre-checkpoint recipient read; never presented as fast authority."""

        state = cls(Path(root), read_only=True).replay_authority_only()
        records = sorted(
            (
                record
                for record in state.messages.values()
                if record.message.recipient_seat_id == seat_id
                and record.status.value in {"queued", "pulled"}
            ),
            key=lambda record: record.message.cursor,
        )
        token = {
            "schema_version": "atlas.seat-mail-token/1",
            "seat_id": seat_id,
            "revision_cursor": state.event_count,
            "revision_event_id": state.head_event_id,
        }
        changed = previous_mail_token is None or dict(previous_mail_token) != token
        return {
            "schema_version": SEAT_MAIL_FRONTIER_SCHEMA,
            "status": "CURRENT",
            "seat_id": seat_id,
            "changed": changed,
            "mail_token": token,
            "pending_messages": (
                [{**record.message.to_dict(), "status": record.status.value} for record in records]
                if changed
                else None
            ),
            "pending_count": len(records),
            "pending_tip_cursor": max((record.message.cursor for record in records), default=0),
            "read_metrics": {
                "rows_loaded": state.event_count,
                "history_replayed": True,
                "full_state_fallback": True,
            },
            "fidelity_boundary": {
                "status": "LEGACY-DEEP",
                "checkpoint_status": "NO-CHECKPOINT",
                "retirement_trigger": "explicit writer checkpoint adoption",
            },
            "read_only": True,
        }

    @classmethod
    def read_provider_seat_binding(
        cls,
        root: Path,
        *,
        provider_session_ref: str,
        expected_context: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Resolve one provider task from a head-bound index plus its lifecycle proof."""

        if not isinstance(provider_session_ref, str) or not provider_session_ref.strip():
            raise ValueError("provider_session_ref must be a non-empty string")
        epoch = cls.read_authority_checkpoint(root, expected_context=expected_context)
        if epoch["status"] == "NO-CHECKPOINT":
            return cls._read_provider_seat_binding_legacy_deep(
                root, provider_session_ref=provider_session_ref
            )
        authority = epoch["checkpoint"]["authority"]
        matching = dict(authority["provider_sessions"].get(provider_session_ref, {}))
        matching_seats = sorted(matching)
        if len(matching_seats) > 1:
            status, seat_id, occupancy = "AMBIGUOUS", None, None
        elif matching_seats:
            seat_id = matching_seats[0]
            status, occupancy = "BOUND", matching[seat_id]
        else:
            status, seat_id, occupancy = "UNBOUND", None, None
        checkpoint = epoch["checkpoint"]
        return {
            "schema_version": PROVIDER_SEAT_BINDING_FRONTIER_SCHEMA,
            "status": status,
            "provider_session_ref": provider_session_ref,
            "seat_id": seat_id,
            "occupancy": occupancy,
            "matching_seats": matching_seats,
            "drift_token": {
                "schema_version": "atlas.conceptric-drift-token/1",
                "cursor": checkpoint["cursor"],
                "head_event_id": checkpoint["head_event_id"],
                "head_record_digest": checkpoint["head_record_digest"],
            },
            "retired_generation_membership": authority[
                "retired_generation_membership"
            ],
            "read_metrics": {
                **epoch["read_metrics"],
                "rows_loaded": 1,
                "authority_rows_loaded": 1,
                "authority_scope": "canonical-authority-checkpoint+bounded-suffix",
                "history_replayed": False,
                "provider_snapshot_materialized": False,
                "full_state_fallback": False,
            },
            "fidelity_boundary": {
                "status": "CHECKSUMMED-CRUTCH",
                "authority": "head-bound checksummed provider projection",
                "forgeability_residual": (
                    "local write access can forge adjacent checkpoint+digest; "
                    "stopped-writer deep verification remains authoritative"
                ),
                "rollback_crutch": "CR-5639952-HEAD-BOUND-LIVE-AUTHORITY",
            },
            "read_only": True,
        }

    @classmethod
    def read_seat_mail_frontier(
        cls,
        root: Path,
        *,
        seat_id: str,
        previous_mail_token: Mapping[str, Any] | None = None,
        expected_context: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Read one head-bound recipient frontier without materialising provider state.

        The ledger tip proves which disposable projection generation is current.  A seat-local
        revision token then avoids loading even that seat's pending rows after unrelated Atlas
        writes.  Missing or stale projection state refuses: a writable Atlas face may rebuild the
        cache from verified history, but this read path never silently falls back to global state.
        """

        if not isinstance(seat_id, str) or not seat_id.strip():
            raise ValueError("seat_id must be a non-empty string")
        if previous_mail_token is not None and not isinstance(previous_mail_token, Mapping):
            raise ValueError("previous_mail_token must be a mapping")
        epoch = cls.read_authority_checkpoint(root, expected_context=expected_context)
        if epoch["status"] == "NO-CHECKPOINT":
            return cls._read_seat_mail_frontier_legacy_deep(
                root,
                seat_id=seat_id,
                previous_mail_token=previous_mail_token,
            )
        checkpoint = epoch["checkpoint"]
        authority = checkpoint["authority"]
        recipient = authority["recipient_mail"].get(
            seat_id,
            {"revision_cursor": 0, "revision_event_id": None, "pending": {}},
        )
        mail_token = {
            "schema_version": "atlas.seat-mail-token/1",
            "seat_id": seat_id,
            "revision_cursor": int(recipient["revision_cursor"]),
            "revision_event_id": recipient["revision_event_id"],
        }
        changed = previous_mail_token is None or dict(previous_mail_token) != mail_token
        pending = None
        if changed:
            pending = []
            for record in sorted(
                recipient["pending"].values(),
                key=lambda item: int(item["message"]["cursor"]),
            ):
                visible = dict(record["message"])
                visible["status"] = record["status"]
                pending.append(visible)
        pending_count = len(recipient["pending"])
        pending_tip = max(
            (int(record["message"]["cursor"]) for record in recipient["pending"].values()),
            default=0,
        )
        return {
            "schema_version": SEAT_MAIL_FRONTIER_SCHEMA,
            "status": "CURRENT",
            "seat_id": seat_id,
            "changed": changed,
            "drift_token": {
                "schema_version": "atlas.conceptric-drift-token/1",
                "cursor": checkpoint["cursor"],
                "head_event_id": checkpoint["head_event_id"],
                "head_record_digest": checkpoint["head_record_digest"],
            },
            "mail_token": mail_token,
            "pending_messages": pending,
            "pending_count": pending_count,
            "pending_tip_cursor": pending_tip,
            "seat_mail_frontier_root": authority["seat_mail_frontier_root"],
            "read_metrics": {
                **epoch["read_metrics"],
                "rows_loaded": 0 if pending is None else len(pending),
                "history_replayed": False,
                "provider_snapshot_materialized": False,
                "full_state_fallback": False,
            },
            "fidelity_boundary": {
                "status": "CHECKSUMMED-CRUTCH",
                "authority": "head-bound checksummed recipient projection",
                "forgeability_residual": (
                    "local write access can forge adjacent checkpoint+digest; "
                    "stopped-writer deep verification remains authoritative"
                ),
                "rollback_crutch": "CR-5639952-HEAD-BOUND-LIVE-AUTHORITY",
            },
            "read_only": True,
        }

    @classmethod
    def prepare_seat_mail_projection(cls, root: Path) -> dict[str, Any]:
        """Rebuild/migrate the disposable mail projection before a new reader activates.

        Construction of one writable face owns the existing projection repair boundary.  This
        transition is accepted only if the canonical ledger head is byte-for-byte unchanged and
        the rebuilt projection receipt names that exact head.  No watcher process is started here.
        """

        root = Path(root)
        before = cls.read_drift_token(root)
        store = cls(root)
        after = cls.read_drift_token(root)
        if before != after:
            raise HistoryChainMismatch(
                "Atlas authority moved during seat-mail projection preparation",
                before=before,
                after=after,
            )
        expected_head = str(after["head_record_digest"])
        if not store._projection_receipt_matches(expected_head=expected_head):
            raise HistoryChainMismatch(
                "seat-mail projection preparation did not reach the canonical head",
                expected_head=expected_head,
            )
        return {
            "schema_version": "atlas.seat-mail-projection-transition/1",
            "status": "READY",
            "authority_head_unchanged": True,
            "authority_cursor": after["cursor"],
            "head_event_id": after["head_event_id"],
            "head_record_digest": expected_head,
            "projection_schema": SEAT_MAIL_PROJECTION_SCHEMA,
            "dependent_projection_schemas": {
                "graph": GRAPH_PROJECTION_SCHEMA,
                "seat_mail": SEAT_MAIL_PROJECTION_SCHEMA,
                "provider_seat_binding": PROVIDER_SEAT_BINDING_FRONTIER_SCHEMA,
            },
            "history_replay_boundary": "schema migration or crash repair only",
            "fidelity_boundary": {
                "status": "CRUTCH",
                "crutch_ids": [
                    "CR-head-bound-disposable-seat-mail-frontier",
                    "CR-head-bound-disposable-provider-seat-binding",
                ],
                "retirement_trigger": (
                    "canonical authenticated accumulators replace both disposable projections"
                ),
            },
            "reader_activation_allowed": True,
        }

    @classmethod
    def _bounded_hived_event(
        cls,
        ledger: sqlite3.Connection,
        hive: CompressedHive,
        event_id: str,
    ) -> StoredEvent:
        raw = ledger.execute(
            "SELECT sequence, previous_digest, record_digest, event_id, event_kind, "
            "assumption, fibre, event_handle FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if raw is None:
            raise HistoryChainMismatch(
                "development review projection cites an absent authority event",
                event_id=event_id,
            )
        face = object.__new__(cls)
        face.hive = hive
        return face._stored_v2_from_raw(raw)

    @classmethod
    def _verify_projected_message_record(
        cls,
        ledger: sqlite3.Connection,
        hive: CompressedHive,
        record: dict[str, Any],
    ) -> SeatMessage:
        """Bind one projected message state to its exact immutable event evidence."""

        try:
            message = SeatMessage.from_dict(record["message"])
            sent_event_id = str(record["sent_event_id"])
            assumption = str(record["assumption"])
            fibre = str(record["fibre"])
            status = str(record["status"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HistoryChainMismatch(
                "development review projection contains an unreadable message record"
            ) from exc
        sent = cls._bounded_hived_event(ledger, hive, sent_event_id)
        if (
            sent.event.kind.value != "seat.message-sent"
            or sent.sequence != message.cursor
            or sent.event.assumption != assumption
            or sent.event.fibre != fibre
            or canonical_json(sent.event.payload) != canonical_json(message.to_dict())
        ):
            raise HistoryChainMismatch(
                "development review projection disagrees with its message send event",
                message_id=message.message_id,
                sent_event_id=sent_event_id,
            )

        pull_event_id = record.get("last_pull_event_id")
        if pull_event_id:
            pulled = cls._bounded_hived_event(ledger, hive, str(pull_event_id)).event
            if (
                pulled.kind.value != "seat.messages-pulled"
                or pulled.assumption != assumption
                or pulled.fibre != fibre
                or pulled.payload.get("seat_id") != message.recipient_seat_id
                or message.message_id not in tuple(pulled.payload.get("message_ids") or ())
            ):
                raise HistoryChainMismatch(
                    "development review projection disagrees with its pull event",
                    message_id=message.message_id,
                    pull_event_id=pull_event_id,
                )
        elif status not in {"queued", "expired", "superseded"}:
            raise HistoryChainMismatch(
                "development review projection claims delivery progress without a pull event",
                message_id=message.message_id,
                status=status,
            )

        acknowledgement_event_id = record.get("acknowledgement_event_id")
        if acknowledgement_event_id:
            acknowledged = cls._bounded_hived_event(
                ledger, hive, str(acknowledgement_event_id)
            ).event
            disposition = str(acknowledged.payload.get("disposition", ""))
            expected_status = {"accepted": "delivered", "refused": "refused"}.get(disposition)
            if (
                acknowledged.kind.value != "seat.message-acknowledged"
                or acknowledged.assumption != assumption
                or acknowledged.fibre != fibre
                or acknowledged.payload.get("message_id") != message.message_id
                or acknowledged.payload.get("seat_id") != message.recipient_seat_id
                or expected_status != status
                or acknowledged.payload.get("reconstruction_handle")
                != record.get("reconstruction_handle")
            ):
                raise HistoryChainMismatch(
                    "development review projection disagrees with its acknowledgement event",
                    message_id=message.message_id,
                    acknowledgement_event_id=acknowledgement_event_id,
                )
        elif status in {"delivered", "refused"}:
            raise HistoryChainMismatch(
                "development review projection claims terminal delivery without acknowledgement",
                message_id=message.message_id,
                status=status,
            )
        if bool(record.get("delivered")) != (status == "delivered"):
            raise HistoryChainMismatch(
                "development review projection has contradictory delivery state",
                message_id=message.message_id,
            )
        return message

    @classmethod
    def _verify_projected_review_row(
        cls,
        ledger: sqlite3.Connection,
        hive: CompressedHive,
        projected: dict[str, Any],
    ) -> bool:
        commission = cls._verify_projected_message_record(ledger, hive, projected["commission"])
        verdict_record = projected.get("verdict")
        if verdict_record is None:
            expected_decision = None
            expected_route_valid = False
            expected_route_errors: tuple[str, ...] = ()
            expected_terminal = False
        else:
            verdict = cls._verify_projected_message_record(ledger, hive, verdict_record)
            expected_route_valid, expected_route_errors = cls._review_route(commission, verdict)
            decision = str(verdict.dependency_roots.get("review_decision", "")).upper()
            expected_decision = (
                decision
                if decision in {"ACCEPT", "REJECT", "CONTEST"}
                else LEGACY_UNTYPED_REVIEW_DECISIONS.get(verdict.message_id)
            )
            expected_terminal = bool(
                expected_route_valid
                and verdict_record.get("status") == "delivered"
                and expected_decision is not None
            )
        legacy_compatibility_verified = bool(
            verdict_record is not None
            and not str(verdict.dependency_roots.get("review_decision", ""))
            and verdict.message_id in LEGACY_UNTYPED_REVIEW_DECISIONS
        )
        expected = {
            "review_decision": expected_decision,
            "route_valid": expected_route_valid,
            "route_errors": list(expected_route_errors),
            "projection_terminal": expected_terminal,
        }
        disagreements = {
            key: {"expected": value, "got": projected.get(key)}
            for key, value in expected.items()
            if projected.get(key) != value
        }
        if (
            verdict_record is not None
            and expected_decision is None
            and not legacy_compatibility_verified
        ):
            disagreements["verdict.legacy_compatibility"] = {
                "expected": "typed review_decision or exact legacy verdict id",
                "got": verdict.message_id,
            }
        residue = projected.get("latest_review_residue")
        if residue is not None:
            residue_record = residue.get("message")
            if not isinstance(residue_record, dict):
                disagreements["latest_review_residue"] = {
                    "expected": "typed message evidence",
                    "got": type(residue_record).__name__,
                }
            else:
                residue_verdict = cls._verify_projected_message_record(ledger, hive, residue_record)
                _valid, residue_errors = cls._review_route(commission, residue_verdict)
                declared_errors = tuple(residue.get("route_errors") or ())
                if not set(residue_errors).issubset(set(declared_errors)):
                    disagreements["latest_review_residue.route_errors"] = {
                        "expected_at_least": list(residue_errors),
                        "got": list(declared_errors),
                    }
        if disagreements:
            raise HistoryChainMismatch(
                "development review projection fidelity check failed",
                commission_id=commission.message_id,
                disagreements=disagreements,
                action="open one current writable Atlas face to rebuild from authority",
            )
        return legacy_compatibility_verified

    @classmethod
    def read_development_review_frontier(
        cls,
        root: Path,
        *,
        terminal_cap: int = 6,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        """Read the head-bound replaceable work frontier without replaying history.

        The canonical ledger remains append-only.  This reads a disposable projection that is
        accepted only when its schema and authoritative head exactly match the compact ledger tip.
        Every unresolved publication is returned; terminal history is an indexed bounded tail.
        Missing/stale/corrupt projection bytes refuse loudly and are repaired only by a writer.
        """

        if isinstance(terminal_cap, bool) or not isinstance(terminal_cap, int) or terminal_cap < 1:
            raise ValueError("terminal_cap must be a positive integer")
        authority_observed_at = observed_at or (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        root = Path(root)
        # Construct only the coordination lock face.  Calling the ordinary constructor here would
        # replay the ledger before reaching the projection and defeat the entire O(open + cap)
        # contract this method exists to provide.
        lock_face = object.__new__(cls)
        lock_face.root = root
        lock_face.lock_path = root / "conceptric.lock"
        lock_face.read_only = True
        ledger_path = root / "conceptric.sqlite3"
        projection_path = root / "conceptric.index.sqlite3"
        with lock_face._locked(shared=True):
            try:
                with cls._open_sqlite(ledger_path, read_only=True) as ledger:
                    schema = cls._schema_version(ledger)
                    if schema != CONCEPTRIC_DB_SCHEMA:
                        raise StoreError(
                            "bounded review frontier requires the hived Atlas ledger",
                            expected=CONCEPTRIC_DB_SCHEMA,
                            got=schema,
                        )
                    tip = ledger.execute(
                        "SELECT sequence, record_digest, event_id FROM events "
                        "ORDER BY sequence DESC LIMIT 1"
                    ).fetchone()
                cursor = 0 if tip is None else int(tip["sequence"])
                head_digest = GENESIS_DIGEST if tip is None else str(tip["record_digest"])
                head_event_id = None if tip is None else str(tip["event_id"])

                with cls._open_sqlite(projection_path, read_only=True) as projection:
                    meta = {
                        row["key"]: row["value"]
                        for row in projection.execute(
                            "SELECT key, value FROM meta WHERE key IN "
                            "('graph_projection_schema', 'authoritative_head_digest', "
                            "'development_review_projection_schema', "
                            "'development_review_head_digest', "
                            "'active_assumption', 'active_fibre', 'projected_event_count', "
                            "'projected_head_event_id')"
                        )
                    }
                    expected_meta = {
                        "graph_projection_schema": GRAPH_PROJECTION_SCHEMA,
                        "authoritative_head_digest": head_digest,
                        "development_review_projection_schema": (
                            DEVELOPMENT_REVIEW_PROJECTION_SCHEMA
                        ),
                        "development_review_head_digest": head_digest,
                        "projected_event_count": str(cursor),
                        "projected_head_event_id": head_event_id or "",
                    }
                    disagreements = {
                        key: {"expected": value, "got": meta.get(key)}
                        for key, value in expected_meta.items()
                        if meta.get(key) != value
                    }
                    if disagreements:
                        raise HistoryChainMismatch(
                            "development review frontier is stale or unknown",
                            disagreements=disagreements,
                            action="open one writable Atlas face to rebuild the disposable projection",
                        )
                    assumption = meta.get("active_assumption", "")
                    fibre = meta.get("active_fibre", "")
                    counts = projection.execute(
                        "SELECT open_count, terminal_count "
                        "FROM development_review_counts WHERE assumption = ? AND fibre = ?",
                        (assumption, fibre),
                    ).fetchone()
                    open_count = 0 if counts is None else int(counts["open_count"])
                    terminal_count = 0 if counts is None else int(counts["terminal_count"])
                    open_rows = tuple(
                        projection.execute(
                            "SELECT * FROM development_reviews "
                            "WHERE assumption = ? AND fibre = ? AND is_terminal = 0 "
                            "ORDER BY commission_cursor",
                            (assumption, fibre),
                        )
                    )
                    terminal_rows_desc = tuple(
                        projection.execute(
                            "SELECT * FROM development_reviews "
                            "WHERE assumption = ? AND fibre = ? AND is_terminal = 1 "
                            "ORDER BY commission_cursor DESC LIMIT ?",
                            (assumption, fibre, terminal_cap),
                        )
                    )
                    occupancy = {
                        row["seat_id"]: json.loads(str(row["occupancy_json"]))
                        for row in projection.execute(
                            "SELECT seat_id, occupancy_json "
                            "FROM seat_occupancy_projection ORDER BY seat_id"
                        )
                    }
                    leases = {
                        row["lease_id"]: effective_region_lease_projection(
                            json.loads(str(row["lease_json"])),
                            seat_occupancies=occupancy,
                            observed_at=authority_observed_at,
                        )
                        for row in projection.execute(
                            "SELECT lease_id, lease_json "
                            "FROM region_lease_projection ORDER BY lease_id"
                        )
                    }
            except (AtlasError, sqlite3.Error):
                raise

        def materialize(row: sqlite3.Row) -> dict[str, Any]:
            return {
                "commission": json.loads(str(row["commission_json"])),
                "verdict": (
                    None if row["verdict_json"] is None else json.loads(str(row["verdict_json"]))
                ),
                "review_decision": row["review_decision"],
                "route_valid": bool(row["route_valid"]),
                "route_errors": json.loads(str(row["route_errors_json"])),
                "review_residue_count": int(row["residue_count"]),
                "latest_review_residue": (
                    None
                    if row["latest_residue_json"] is None
                    else json.loads(str(row["latest_residue_json"]))
                ),
                "projection_terminal": bool(row["is_terminal"]),
            }

        rows = [
            *(materialize(row) for row in open_rows),
            *(materialize(row) for row in reversed(terminal_rows_desc)),
        ]
        rows.sort(key=lambda item: int(item["commission"]["message"]["cursor"]))
        if open_count != len(open_rows):
            raise HistoryChainMismatch(
                "development review open aggregate disagrees with visible rows",
                projected_open_count=open_count,
                visible_open_rows=len(open_rows),
            )
        if terminal_count < len(terminal_rows_desc):
            raise HistoryChainMismatch(
                "development review terminal aggregate is smaller than its visible tail",
                projected_terminal_count=terminal_count,
                visible_terminal_rows=len(terminal_rows_desc),
            )
        # Re-enter the shared lock and bind every row that will be served to exact hived events.
        # If a writer advanced in the small interval after the projection snapshot, the captured
        # head no longer matches and this read refuses instead of returning a mixed coordinate.
        with (
            lock_face._locked(shared=True),
            cls._open_sqlite(ledger_path, read_only=True) as evidence_ledger,
        ):
            live_tip = evidence_ledger.execute(
                "SELECT sequence, record_digest, event_id FROM events "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            live_cursor = 0 if live_tip is None else int(live_tip["sequence"])
            live_digest = GENESIS_DIGEST if live_tip is None else str(live_tip["record_digest"])
            live_event_id = None if live_tip is None else str(live_tip["event_id"])
            if (live_cursor, live_digest, live_event_id) != (
                cursor,
                head_digest,
                head_event_id,
            ):
                raise HistoryChainMismatch(
                    "development review frontier moved during bounded verification",
                    captured_cursor=cursor,
                    live_cursor=live_cursor,
                )
            hive_ref = evidence_ledger.execute(
                "SELECT value FROM meta WHERE key = 'event_hive_ref'"
            ).fetchone()
            if hive_ref is None:
                raise StoreError("bounded review frontier has no event hive reference")
            hive_path = Path(str(hive_ref["value"]))
            if not hive_path.is_absolute():
                hive_path = root / hive_path
            hive = CompressedHive(hive_path)
            for projected in rows:
                projected["legacy_compatibility_verified"] = cls._verify_projected_review_row(
                    evidence_ledger, hive, projected
                )
        return {
            "schema_version": DEVELOPMENT_REVIEW_FRONTIER_SCHEMA,
            "status": "CURRENT",
            "active_context": {
                "assumption": assumption or None,
                "fibre": fibre or None,
            },
            "caused_by_event_cursor": cursor,
            "head_event_id": head_event_id,
            "head_record_digest": head_digest,
            "rows": rows,
            "projection_open_count": open_count,
            "projection_terminal_count": terminal_count,
            "omitted_projection_terminal_count": max(0, terminal_count - len(terminal_rows_desc)),
            "seat_occupancy": occupancy,
            "region_leases": leases,
            "region_lease_authority_observed_at": authority_observed_at,
            "read_metrics": {
                "open_rows_loaded": len(open_rows),
                "terminal_rows_loaded": len(terminal_rows_desc),
                "rows_loaded": len(rows),
                "terminal_cap": terminal_cap,
                "history_replayed": False,
                "provider_snapshot_materialized": False,
                "visible_rows_ledger_verified": len(rows),
                "open_aggregate_verified": True,
            },
            "fidelity_boundary": {
                "status": "CRUTCH",
                "crutch_id": ("CR-review-frontier-terminal-aggregate-without-authoritative-root"),
                "visible_rows": "exact hived send, pull and acknowledgement evidence",
                "open_aggregate": "exactly equals the complete visible open-row set",
                "terminal_aggregate": (
                    "head-bound disposable count; no canonical authenticated accumulator yet"
                ),
            },
            "read_only": True,
        }

    def _refresh_verified_head_if_needed(
        self,
        connection: sqlite3.Connection,
        *,
        repair_projection: bool = True,
    ) -> None:
        with self._verified_cache_lock:
            self._refresh_verified_head_if_needed_locked(
                connection, repair_projection=repair_projection
            )

    def _refresh_verified_head_if_needed_locked(
        self,
        connection: sqlite3.Connection,
        *,
        repair_projection: bool = True,
    ) -> None:
        """Fold a verified external suffix instead of replaying history on every writer drift.

        The cached state was fully verified when this store instance opened.  A concurrent
        provider commonly advances the same ledger by only one or two events; re-inflating every
        historical hive for that move makes one fabric append scale with the life of the Atlas.
        Verify the content-addressed suffix and its exact predecessor instead.  Full replay stays
        the refusal-safe fallback for regression, discontinuity, or a ledger/projection crash seam.
        """

        sequence, digest = self._compact_tip(connection)
        if (sequence, digest) == (self._verified_sequence, self._verified_head_digest):
            return
        if sequence > self._verified_sequence:
            suffix = self._read_v2_suffix_from(
                connection,
                after_sequence=self._verified_sequence,
                previous_digest=self._verified_head_digest,
            )
            if not suffix or suffix[-1].sequence != sequence or suffix[-1].record_digest != digest:
                raise HistoryChainMismatch(
                    "verified history suffix does not reach the compact authoritative tip",
                    expected_sequence=sequence,
                    got_sequence=None if not suffix else suffix[-1].sequence,
                    expected_digest=digest,
                    got_digest=None if not suffix else suffix[-1].record_digest,
                )
            state = self._verified_state
            for row in suffix:
                state = apply_event(state, row.event)
            if not repair_projection or self._projection_receipt_matches(expected_head=digest):
                self._verified_state = state
                self._verified_sequence = sequence
                self._verified_head_digest = digest
                return

        rows = self._read_v2_rows_from(connection)
        self._prime_verified_head(rows)
        if repair_projection:
            # A writer may have committed authority and died before refreshing the disposable
            # index. The explicit write-face refresh repairs it before accepting a delta.
            self._ensure_projection(rows)

    def _projection_receipt_matches(self, *, expected_head: str) -> bool:
        """Cheap crash-seam check; content poison is repaired by replay, never trusted here."""

        if not self.projection_path.is_file():
            return False
        try:
            with self._open_sqlite(self.projection_path, read_only=True) as projection:
                schema = projection.execute(
                    "SELECT value FROM meta WHERE key = 'graph_projection_schema'"
                ).fetchone()
                head = projection.execute(
                    "SELECT value FROM meta WHERE key = 'authoritative_head_digest'"
                ).fetchone()
                review_schema = projection.execute(
                    "SELECT value FROM meta WHERE key = 'development_review_projection_schema'"
                ).fetchone()
                review_head = projection.execute(
                    "SELECT value FROM meta WHERE key = 'development_review_head_digest'"
                ).fetchone()
                mail_schema = projection.execute(
                    "SELECT value FROM meta WHERE key = 'seat_mail_projection_schema'"
                ).fetchone()
                mail_head = projection.execute(
                    "SELECT value FROM meta WHERE key = 'seat_mail_head_digest'"
                ).fetchone()
                return bool(
                    schema is not None
                    and schema["value"] == GRAPH_PROJECTION_SCHEMA
                    and head is not None
                    and head["value"] == expected_head
                    and review_schema is not None
                    and review_schema["value"] == DEVELOPMENT_REVIEW_PROJECTION_SCHEMA
                    and review_head is not None
                    and review_head["value"] == expected_head
                    and mail_schema is not None
                    and mail_schema["value"] == SEAT_MAIL_PROJECTION_SCHEMA
                    and mail_head is not None
                    and mail_head["value"] == expected_head
                )
        except (AtlasError, sqlite3.Error):
            return False

    @staticmethod
    def _verify_graph_projection(
        connection: sqlite3.Connection,
        state: ConceptricState,
        rows: tuple[StoredEvent, ...] | None = None,
    ) -> None:
        stored_objects = {
            row["object_id"]: row["object_json"]
            for row in connection.execute("SELECT object_id, object_json FROM objects")
        }
        expected_objects = {
            object_id: canonical_json(item.to_dict())
            for object_id, item in state.graph_objects.items()
        }
        stored_edges = {
            row["edge_id"]: row["edge_json"]
            for row in connection.execute("SELECT edge_id, edge_json FROM edges")
        }
        expected_edges = {
            edge_id: canonical_json(edge.to_dict()) for edge_id, edge in state.graph_edges.items()
        }
        if stored_objects != expected_objects or stored_edges != expected_edges:
            raise HistoryChainMismatch(
                "normalized graph projection disagrees with event replay",
                stored_objects=len(stored_objects),
                expected_objects=len(expected_objects),
                stored_edges=len(stored_edges),
                expected_edges=len(expected_edges),
            )

        expected = sqlite3.connect(":memory:")
        expected.row_factory = sqlite3.Row
        try:
            ConceptricStore._create_projection_schema(expected)
            for record in sorted(state.messages.values(), key=lambda item: item.message.cursor):
                ConceptricStore._project_review_record(expected, record)
            expected_reviews = {
                row["commission_id"]: tuple(row)
                for row in expected.execute(
                    "SELECT * FROM development_reviews ORDER BY commission_id"
                )
            }
            expected_counts = {
                (row["assumption"], row["fibre"]): tuple(row)
                for row in expected.execute(
                    "SELECT * FROM development_review_counts ORDER BY assumption, fibre"
                )
            }
        finally:
            expected.close()
        stored_reviews = {
            row["commission_id"]: tuple(row)
            for row in connection.execute(
                "SELECT * FROM development_reviews ORDER BY commission_id"
            )
        }
        stored_counts = {
            (row["assumption"], row["fibre"]): tuple(row)
            for row in connection.execute(
                "SELECT * FROM development_review_counts ORDER BY assumption, fibre"
            )
        }
        if stored_reviews != expected_reviews or stored_counts != expected_counts:
            raise HistoryChainMismatch(
                "development review projection disagrees with event replay",
                stored_reviews=len(stored_reviews),
                expected_reviews=len(expected_reviews),
                stored_context_counts=len(stored_counts),
                expected_context_counts=len(expected_counts),
            )

        stored_occupancy = {
            row["seat_id"]: row["occupancy_json"]
            for row in connection.execute(
                "SELECT seat_id, occupancy_json FROM seat_occupancy_projection"
            )
        }
        expected_occupancy = {
            seat_id: canonical_json(occupancy.to_dict())
            for seat_id, occupancy in state.seat_occupancies.items()
        }
        stored_provider_sessions = {
            (row["provider_session_ref"], row["seat_id"]): row["occupancy_json"]
            for row in connection.execute(
                "SELECT provider_session_ref, seat_id, occupancy_json "
                "FROM provider_session_seat_projection"
            )
        }
        expected_provider_sessions = {
            (occupancy.binding.provider_session_ref, seat_id): canonical_json(occupancy.to_dict())
            for seat_id, occupancy in state.seat_occupancies.items()
            if occupancy.routing_authority and occupancy.binding is not None
        }
        stored_leases = {
            row["lease_id"]: row["lease_json"]
            for row in connection.execute(
                "SELECT lease_id, lease_json FROM region_lease_projection"
            )
        }
        expected_leases = {
            lease_id: canonical_json(lease.to_dict())
            for lease_id, lease in state.region_leases.items()
        }
        if (
            stored_occupancy != expected_occupancy
            or stored_provider_sessions != expected_provider_sessions
            or stored_leases != expected_leases
        ):
            raise HistoryChainMismatch(
                "coordination frontier projection disagrees with event replay"
            )

        stored_mail = {
            row["message_id"]: (
                row["recipient_seat_id"],
                int(row["cursor"]),
                row["message_state_json"],
            )
            for row in connection.execute(
                "SELECT message_id, recipient_seat_id, cursor, message_state_json "
                "FROM seat_mail_pending ORDER BY message_id"
            )
        }
        expected_mail = {
            message_id: (
                record.message.recipient_seat_id,
                record.message.cursor,
                canonical_json(record.to_dict()),
            )
            for message_id, record in state.messages.items()
            if record.status.value in {"queued", "pulled"}
        }
        if stored_mail != expected_mail:
            raise HistoryChainMismatch(
                "seat mail projection disagrees with event replay",
                stored_pending=len(stored_mail),
                expected_pending=len(expected_mail),
            )
        recipients = {record.message.recipient_seat_id for record in state.messages.values()}
        if recipients and rows is None:
            raise HistoryChainMismatch(
                "seat mail frontier verification requires its canonical event rows"
            )
        exact_revisions: dict[str, tuple[int, str]] = {}
        if rows is not None:
            replayed = ConceptricState()
            for stored in rows:
                next_state = apply_event(replayed, stored.event)
                changed_messages = {
                    message_id
                    for message_id, record in next_state.messages.items()
                    if replayed.messages.get(message_id) != record
                }
                for message_id in changed_messages:
                    recipient = next_state.messages[message_id].message.recipient_seat_id
                    exact_revisions[recipient] = (
                        next_state.event_count,
                        stored.event.event_id,
                    )
                replayed = next_state
            if replayed != state:
                raise HistoryChainMismatch(
                    "seat mail frontier verification replay disagrees with supplied state"
                )
        stored_frontiers = {
            row["seat_id"]: row
            for row in connection.execute(
                "SELECT seat_id, revision_cursor, revision_event_id, "
                "pending_count, pending_tip_cursor FROM seat_mail_frontiers"
            )
        }
        if set(stored_frontiers) != recipients:
            raise HistoryChainMismatch(
                "seat mail frontier recipients disagree with event replay",
                stored=sorted(stored_frontiers),
                expected=sorted(recipients),
            )
        for seat_id in sorted(recipients):
            row = stored_frontiers[seat_id]
            cursors = [
                record.message.cursor
                for record in state.messages.values()
                if record.message.recipient_seat_id == seat_id
                and record.status.value in {"queued", "pulled"}
            ]
            expected_revision = exact_revisions.get(seat_id)
            if (
                int(row["pending_count"]) != len(cursors)
                or int(row["pending_tip_cursor"]) != max(cursors, default=0)
                or expected_revision is None
                or int(row["revision_cursor"]) != expected_revision[0]
                or row["revision_event_id"] != expected_revision[1]
            ):
                raise HistoryChainMismatch(
                    "seat mail frontier aggregate disagrees with event replay",
                    seat_id=seat_id,
                )
        projected_meta = {
            row["key"]: row["value"]
            for row in connection.execute(
                "SELECT key, value FROM meta WHERE key IN "
                "('active_assumption', 'active_fibre', 'projected_event_count', "
                "'projected_head_event_id')"
            )
        }
        expected_meta = {
            "active_assumption": state.active_assumption or "",
            "active_fibre": state.active_fibre or "",
            "projected_event_count": str(state.event_count),
            "projected_head_event_id": state.head_event_id or "",
        }
        if projected_meta != expected_meta:
            raise HistoryChainMismatch(
                "live frontier metadata disagrees with event replay",
                stored=projected_meta,
                expected=expected_meta,
            )

    def _verify_or_reconstruct_projection(
        self, rows: tuple[StoredEvent, ...], state: ConceptricState
    ) -> None:
        """Verify the disposable index, rebuilding it ephemerally on a read-only face.

        A schema-v2 clone deliberately need not ship ``conceptric.index.sqlite3``.  A writer can
        rebuild that cache on disk; a read-only process instead reconstructs the same normalized
        graph in memory.  Missing, stale or damaged *authority* has already refused while reading
        ``rows`` and the hives, so falling back here weakens no canonical check.
        """

        if self.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA:
            with self._open_sqlite(
                self.path, read_only=True, immutable=self.immutable
            ) as projection:
                self._verify_graph_projection(projection, state, rows)
            return
        if not self.read_only:
            # Verify through a read-only descriptor first. If any cache invariant fails, this
            # writable face owns the exclusive store lock and can atomically reconstruct it.
            try:
                with self._open_sqlite(self.projection_path, read_only=True) as projection:
                    schema = projection.execute(
                        "SELECT value FROM meta WHERE key = 'graph_projection_schema'"
                    ).fetchone()
                    head = projection.execute(
                        "SELECT value FROM meta WHERE key = 'authoritative_head_digest'"
                    ).fetchone()
                    if (
                        schema is None
                        or schema["value"] != GRAPH_PROJECTION_SCHEMA
                        or head is None
                        or head["value"] != self._head_digest(rows)
                    ):
                        raise HistoryChainMismatch(
                            "disposable graph projection is stale",
                            expected_schema=GRAPH_PROJECTION_SCHEMA,
                            expected_head=self._head_digest(rows),
                        )
                    self._verify_graph_projection(projection, state, rows)
            except (AtlasError, sqlite3.Error):
                self._replace_graph_projection(rows)
            return

        if self.projection_path.is_file():
            try:
                with self._connect_projection() as projection:
                    schema = projection.execute(
                        "SELECT value FROM meta WHERE key = 'graph_projection_schema'"
                    ).fetchone()
                    head = projection.execute(
                        "SELECT value FROM meta WHERE key = 'authoritative_head_digest'"
                    ).fetchone()
                    if (
                        schema is None
                        or schema["value"] != GRAPH_PROJECTION_SCHEMA
                        or head is None
                        or head["value"] != self._head_digest(rows)
                    ):
                        raise HistoryChainMismatch(
                            "disposable graph projection is stale",
                            expected_schema=GRAPH_PROJECTION_SCHEMA,
                            expected_head=self._head_digest(rows),
                        )
                    self._verify_graph_projection(projection, state, rows)
                    return
            except (AtlasError, sqlite3.Error):
                # The projection has no authority.  Reconstruct it below without writing to the
                # clone; errors in the ledger/hive path were raised before this branch.
                pass

        projection = sqlite3.connect(":memory:")
        projection.row_factory = sqlite3.Row
        projection.execute("PRAGMA foreign_keys = ON")
        try:
            self._create_projection_schema(projection)
            projection.commit()
            self._rebuild_graph_projection(
                projection, rows, projection_schema=GRAPH_PROJECTION_SCHEMA
            )
            self._verify_graph_projection(projection, state, rows)
        finally:
            projection.close()

    @classmethod
    def read_event_descent(
        cls, root: Path, *, before: int | None = None, limit: int = 8,
        kind: str | None = None, event_id: str | None = None,
        expected_head: str | None = None,
    ) -> dict[str, Any]:
        """Bounded, verified ledger descent without constructing/replaying a store.

        A transaction binds the page to one tip. The continuation pins that tip;
        each selected envelope is hash-checked against its ledger row. No directory
        discovery, sidecar regeneration, authority adoption, or canonical write occurs.
        """
        if not 1 <= limit <= 32 or (before is not None and before < 1):
            raise StoreError("invalid event descent bounds", code="BUDGET")
        root = Path(root)
        with cls._open_sqlite(root / "conceptric.sqlite3", read_only=True) as ledger:
            ledger.execute("BEGIN")
            if cls._schema_version(ledger) != CONCEPTRIC_DB_SCHEMA:
                raise StoreError("entry requires a hived ledger", code="UNAVAILABLE")
            tip = ledger.execute("SELECT sequence, record_digest FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
            head = GENESIS_DIGEST if tip is None else str(tip["record_digest"])
            if expected_head is not None and head != expected_head:
                raise HistoryChainMismatch("entry moved; restart from the root", code="MOVED")
            hive_row = ledger.execute("SELECT value FROM meta WHERE key = 'event_hive_ref'").fetchone()
            if hive_row is None:
                raise StoreError("entry has no event hive", code="UNAVAILABLE")
            hive_path = Path(str(hive_row["value"]))
            face = object.__new__(cls)
            face.hive = CompressedHive(hive_path if hive_path.is_absolute() else root / hive_path)
            where, values = ["sequence < ?"], [before or ((int(tip["sequence"]) + 1) if tip else 1)]
            if kind is not None:
                where.append("event_kind = ?")
                values.append(kind)
            if event_id is not None:
                where.append("event_id = ?")
                values.append(event_id)
            raw = tuple(ledger.execute(
                "SELECT * FROM events WHERE " + " AND ".join(where) +
                " ORDER BY sequence DESC LIMIT ?", (*values, limit + 1)))
            selected = raw[:limit]
            events = []
            for row in selected:
                stored = face._stored_v2_from_raw(row)
                prior = ledger.execute("SELECT record_digest FROM events WHERE sequence = ?",
                                       (stored.sequence - 1,)).fetchone()
                previous = GENESIS_DIGEST if stored.sequence == 1 else (None if prior is None else str(prior[0]))
                if stored.previous_digest != previous:
                    raise HistoryChainMismatch("entry row is detached from its predecessor", sequence=stored.sequence)
                events.append({"sequence": stored.sequence, "event_handle": str(row["event_handle"]),
                               "event": stored.event.to_dict()})
            return {"head": head, "event_count": 0 if tip is None else int(tip["sequence"]),
                    "events": events, "next_before": int(selected[-1]["sequence"]) if len(raw) > limit else None,
                    "enumerated_store_dirs": False}

    def events(self) -> tuple[AtlasEvent, ...]:
        with self._locked(shared=True):
            return tuple(row.event for row in self._read_rows())

    def _hive_reachability_unlocked(self) -> dict[str, Any]:
        """Derive a head-bound mark receipt without deleting an unreferenced chunk.

        The caller owns the store lock.  The ledger is the mark set.  Every marked chunk is read
        and hash-verified; extra chunks are named as orphans and retained until a separately
        authorized GC act consumes this receipt.  A malformed filename is residue too, never
        silently skipped.
        """

        with self._connect() as connection:
            self._refresh_schema(connection)
            if self.schema_version != CONCEPTRIC_DB_SCHEMA:
                return {
                    "schema_version": "atlas.hive-reachability/1",
                    "status": "legacy-monolith",
                    "ledger_schema": self.schema_version,
                    "event_count": len(self._read_rows_from(connection)),
                }
            ledger_rows = tuple(
                connection.execute(
                    "SELECT sequence, record_digest, event_handle FROM events ORDER BY sequence"
                )
            )
        ledger_handles = tuple(row["event_handle"] for row in ledger_rows)
        for handle in ledger_handles:
            self.hive.get(handle)

        stored_handles: set[str] = set()
        invalid_paths: list[str] = []
        if self.hive_root.exists():
            for path in sorted(item for item in self.hive_root.rglob("*") if item.is_file()):
                if path.is_symlink() or not path.name.endswith(".zlib"):
                    invalid_paths.append(str(path.relative_to(self.hive_root)))
                    continue
                stem = path.name.removesuffix(".zlib")
                if len(stem) != 64 or any(char not in "0123456789abcdef" for char in stem):
                    invalid_paths.append(str(path.relative_to(self.hive_root)))
                    continue
                handle = HASH_PREFIX + stem
                if self.hive.key_path(handle) != path:
                    invalid_paths.append(str(path.relative_to(self.hive_root)))
                    continue
                stored_handles.add(handle)
        marked = set(ledger_handles)
        missing = tuple(sorted(marked - stored_handles))
        if missing:
            # ``get`` above normally raises first; keep this guard for an impossible race.
            raise BlobMissing("marked hive chunks disappeared during reachability", keys=missing)
        orphans = tuple(sorted(stored_handles - marked))
        head = GENESIS_DIGEST if not ledger_rows else ledger_rows[-1]["record_digest"]
        return {
            "schema_version": "atlas.hive-reachability/1",
            "status": "exact" if not invalid_paths else "residue",
            "ledger_schema": self.schema_version,
            "ledger_head_digest": head,
            "event_count": len(ledger_rows),
            "unique_marked_chunks": len(marked),
            "stored_chunks": len(stored_handles),
            "marked_handles_root": chash(
                {
                    "schema_version": "atlas.hive-mark-set/1",
                    "handles": sorted(marked),
                }
            ),
            "orphan_handles": orphans,
            "orphan_handles_root": chash(
                {
                    "schema_version": "atlas.hive-orphan-set/1",
                    "handles": orphans,
                }
            ),
            "invalid_paths": tuple(invalid_paths),
            "retention": "all-marked; orphans-named-not-deleted",
        }

    def hive_reachability(self) -> dict[str, Any]:
        """Derive a stable head-bound mark receipt under one shared authority snapshot."""

        with self._locked(shared=True):
            return self._hive_reachability_unlocked()

    @staticmethod
    def _read_receipt(path: Path, *, schema: str) -> dict[str, Any]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StoreError(
                "Atlas custody receipt is absent or unreadable",
                path=str(path),
                expected_schema=schema,
                error=str(exc),
            ) from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != schema:
            raise StoreError(
                "Atlas custody receipt schema is unknown",
                path=str(path),
                expected_schema=schema,
                got=raw.get("schema_version") if isinstance(raw, dict) else type(raw).__name__,
            )
        return raw

    @staticmethod
    def _meta_values(connection: sqlite3.Connection) -> dict[str, str]:
        return {
            str(row["key"]): str(row["value"])
            for row in connection.execute("SELECT key, value FROM meta ORDER BY key")
        }

    @staticmethod
    def _event_prefix_root(rows: Iterable[StoredEvent]) -> str:
        """Streaming content root for one exact causal prefix.

        The migration receipt must be derivable from the surviving ledger itself. A
        source-database hash copied into both receipt and metadata is only a travelling
        assertion; this root commits the verified StoredEvent sequence that the v2 ledger
        actually preserves without materialising an unbounded JSON list.
        """
        import hashlib

        digest = hashlib.sha256()
        digest.update(b"atlas.migration-event-prefix/1\0")
        for row in rows:
            encoded = canonical_json(row.to_dict()).encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
        return HASH_PREFIX + digest.hexdigest()

    def _validate_store_identity(self, identity: Any, *, operation: str) -> dict[str, Any]:
        if not isinstance(identity, dict):
            raise StoreError(f"{operation} has no typed store identity")
        expected_keys = {"schema_version", "role", "database_ref"}
        if set(identity) != expected_keys:
            raise StoreError(
                f"{operation} store identity shape is unknown",
                expected=sorted(expected_keys),
                got=sorted(str(key) for key in identity),
            )
        role = identity.get("role")
        if not isinstance(role, str):
            raise StoreError(f"{operation} store role is not a string", role=role)
        role = role.strip()
        role_tokens = set(role.casefold().replace("_", "-").split("-"))
        if not role or role_tokens.intersection({"prod", "production"}):
            raise StoreError(
                f"{operation} requires a concrete non-production store role",
                store_role=role,
            )
        expected = {
            "schema_version": "atlas.store-identity/1",
            "role": role,
            "database_ref": self.path.name,
        }
        if identity != expected:
            raise StoreError(
                f"{operation} store identity disagrees with this ledger",
                expected=expected,
                got=identity,
            )
        if self._expected_store_role is not None and role != self._expected_store_role:
            raise StoreError(
                f"{operation} store role disagrees with the caller's authority anchor",
                expected_role=self._expected_store_role,
                got_role=role,
            )
        return expected

    @staticmethod
    def _custody_claims() -> dict[str, bool]:
        """The claims vocabulary is verified data, never decorative receipt prose."""
        return {
            "all_marked_chunks_present_and_hash_verified": True,
            "zero_orphans": True,
            "wal_checkpointed": True,
            "disposable_projection_authority": False,
        }

    @staticmethod
    def _require_exact_reachability(reachability: dict[str, Any]) -> None:
        if reachability.get("status") != "exact":
            raise StoreError(
                "hived authority contains invalid custody paths",
                status=reachability.get("status"),
                invalid_paths=reachability.get("invalid_paths", ()),
            )
        if reachability.get("orphan_handles"):
            raise StoreError(
                "hived authority contains chunks outside the causal ledger mark set",
                orphan_handles=reachability["orphan_handles"],
            )
        if int(reachability.get("event_count", -1)) != int(
            reachability.get("unique_marked_chunks", -2)
        ):
            # Identical event envelopes may legitimately share a content chunk only if their
            # canonical event ids also match, which the event table forbids.  A count mismatch is
            # therefore not deduplication; it is a broken custody relation.
            raise StoreError(
                "ledger events and unique marked hive chunks disagree",
                event_count=reachability.get("event_count"),
                unique_marked_chunks=reachability.get("unique_marked_chunks"),
            )

    def _migration_custody_projection(
        self,
        rows: tuple[StoredEvent, ...],
        meta: dict[str, str],
        *,
        expected_store_identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify a migration receipt as an immutable prefix, never as a moving head."""

        migration_marked = "migration_source_sha256" in meta
        if not self.migration_receipt_path.is_file():
            if migration_marked:
                raise StoreError(
                    "migrated ledger is missing its causal migration receipt",
                    path=str(self.migration_receipt_path),
                )
            return {"present": False}
        receipt = self._read_receipt(
            self.migration_receipt_path, schema=HIVE_MIGRATION_RECEIPT_SCHEMA
        )
        try:
            migration_status = str(receipt["status"])
            source_schema = str(receipt["source_schema"])
            migrated_count = int(receipt["event_count"])
            migrated_head = str(receipt["head_digest"])
            migrated_ref = str(receipt["event_hive_ref"])
            migrated_codec = str(receipt["event_hive_codec"])
            identity = dict(receipt["store_identity"])
            source_event_chain_root = str(receipt["source_event_chain_root"])
            source_meta_root = str(receipt["source_meta_root"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StoreError(
                "migration receipt is structurally incomplete",
                path=str(self.migration_receipt_path),
            ) from exc
        if migrated_count < 0 or migrated_count > len(rows):
            raise StoreError(
                "migration receipt event count is not a prefix of replay",
                receipt_event_count=migrated_count,
                replay_event_count=len(rows),
            )
        prefix_head = (
            GENESIS_DIGEST if migrated_count == 0 else rows[migrated_count - 1].record_digest
        )
        prefix = rows[:migrated_count]
        prefix_handles = tuple(
            hash_bytes(canonical_json(row.event.to_dict()).encode("utf-8")) for row in prefix
        )
        expected_prefix_root = self._event_prefix_root(prefix)
        expected_mark_root = chash(
            {
                "schema_version": "atlas.hive-mark-set/1",
                "handles": sorted(prefix_handles),
            }
        )
        failures: dict[str, Any] = {}
        expected = {
            "status": "migrated",
            "source_schema": LEGACY_CONCEPTRIC_DB_SCHEMA,
            "target_schema": CONCEPTRIC_DB_SCHEMA,
            "event_hive_ref": meta.get("event_hive_ref"),
            "event_hive_codec": meta.get("event_hive_codec"),
            "head_digest": prefix_head,
            "source_event_chain_root": expected_prefix_root,
            "source_meta_root": meta.get("migration_source_meta_root"),
        }
        got = {
            "status": migration_status,
            "source_schema": source_schema,
            "target_schema": receipt.get("target_schema"),
            "event_hive_ref": migrated_ref,
            "event_hive_codec": migrated_codec,
            "head_digest": migrated_head,
            "source_event_chain_root": source_event_chain_root,
            "source_meta_root": source_meta_root,
        }
        for key, value in expected.items():
            if got[key] != value:
                failures[key] = {"expected": value, "got": got[key]}
        if meta.get("migration_source_sha256") != receipt.get("source_database_sha256"):
            failures["source_database_sha256"] = {
                "expected": meta.get("migration_source_sha256"),
                "got": receipt.get("source_database_sha256"),
            }
        if meta.get("migration_event_count") != str(migrated_count):
            failures["migration_event_count"] = {
                "expected": meta.get("migration_event_count"),
                "got": migrated_count,
            }
        try:
            identity = self._validate_store_identity(
                identity, operation="migration receipt verification"
            )
        except StoreError as exc:
            failures["store_identity_validity"] = str(exc)
        if expected_store_identity is not None and identity != expected_store_identity:
            failures["store_identity"] = {
                "expected": expected_store_identity,
                "got": identity,
            }
        historical_reachability = receipt.get("reachability")
        if not isinstance(historical_reachability, dict):
            failures["reachability"] = "absent"
        else:
            if historical_reachability.get("ledger_head_digest") != migrated_head:
                failures["reachability_head"] = {
                    "expected": migrated_head,
                    "got": historical_reachability.get("ledger_head_digest"),
                }
            if int(historical_reachability.get("event_count", -1)) != migrated_count:
                failures["reachability_event_count"] = {
                    "expected": migrated_count,
                    "got": historical_reachability.get("event_count"),
                }
            if historical_reachability.get("status") != "exact":
                failures["reachability_status"] = historical_reachability.get("status")
            if historical_reachability.get("orphan_handles"):
                failures["reachability_orphans"] = historical_reachability.get("orphan_handles")
            if historical_reachability.get("invalid_paths"):
                failures["reachability_invalid_paths"] = historical_reachability.get(
                    "invalid_paths"
                )
            if int(historical_reachability.get("unique_marked_chunks", -1)) != len(
                set(prefix_handles)
            ):
                failures["reachability_unique_marked_chunks"] = {
                    "expected": len(set(prefix_handles)),
                    "got": historical_reachability.get("unique_marked_chunks"),
                }
            if historical_reachability.get("marked_handles_root") != expected_mark_root:
                failures["reachability_marked_handles_root"] = {
                    "expected": expected_mark_root,
                    "got": historical_reachability.get("marked_handles_root"),
                }
        expected_authorization = {
            "authorizing_fields": (
                "store_identity",
                "status",
                "source_schema",
                "target_schema",
                "source_event_chain_root",
                "event_count",
                "head_digest",
                "event_hive_ref",
                "event_hive_codec",
                "reachability",
            ),
            "historical_source_measurements": (
                "source_database_sha256",
                "source_meta_root",
            ),
            "storage_and_wall_clock_measurements": "absent-non-authorizing",
        }
        if canonical_json(receipt.get("authorization_scope")) != canonical_json(
            expected_authorization
        ):
            failures["authorization_scope"] = {
                "expected": expected_authorization,
                "got": receipt.get("authorization_scope"),
            }
        if failures:
            raise StoreError(
                "migration receipt disagrees with the causal ledger prefix",
                path=str(self.migration_receipt_path),
                failures=failures,
            )
        return {
            "present": True,
            "receipt_sha256": sha256_file(self.migration_receipt_path),
            "event_count": migrated_count,
            "head_digest": migrated_head,
            "store_identity": identity,
        }

    def _custody_authority_paths_root(
        self, reachability: dict[str, Any], *, migration_present: bool
    ) -> str:
        with self._connect() as connection:
            handles = tuple(
                sorted(
                    str(row["event_handle"])
                    for row in connection.execute(
                        "SELECT event_handle FROM events ORDER BY sequence"
                    )
                )
            )
        paths = [self.path.name]
        if migration_present:
            paths.append(self.migration_receipt_path.name)
        paths.extend(self._hive_ref(self.root, self.hive.key_path(handle)) for handle in handles)
        return chash(
            {
                "schema_version": "atlas.hive-custody-path-set/1",
                "ledger_head_digest": reachability["ledger_head_digest"],
                "paths": sorted(paths),
            }
        )

    def _wal_path(self) -> Path:
        return self.path.with_name(self.path.name + "-wal")

    def _refuse_uncheckpointed_authority(self) -> None:
        wal = self._wal_path()
        try:
            size = wal.stat().st_size if wal.exists() else 0
        except OSError as exc:
            raise StoreError(
                "authoritative WAL state could not be inspected", path=str(wal), error=str(exc)
            ) from exc
        if size:
            raise StoreError(
                "commit-shaped Atlas authority has uncheckpointed WAL frames",
                path=str(wal),
                bytes=size,
                action="checkpoint under the write lock and mint a new custody seal",
            )

    def _verify_custody_unlocked(self) -> dict[str, Any]:
        self._refuse_uncheckpointed_authority()
        with self._connect() as connection:
            self._refresh_schema(connection)
            if self.schema_version != CONCEPTRIC_DB_SCHEMA:
                raise StoreError(
                    "commit custody requires a hived schema-v2 ledger",
                    schema=self.schema_version,
                )
            rows = self._read_rows_from(connection)
            meta = self._meta_values(connection)
        reachability = self._hive_reachability_unlocked()
        self._require_exact_reachability(reachability)
        receipt = self._read_receipt(self.custody_receipt_path, schema=HIVE_CUSTODY_RECEIPT_SCHEMA)
        identity = self._validate_store_identity(
            receipt.get("store_identity"), operation="custody verification"
        )
        try:
            ledger_identity = json.loads(meta["store_identity_json"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StoreError(
                "sealed ledger has no readable store identity",
                path=str(self.path),
            ) from exc
        ledger_identity = self._validate_store_identity(
            ledger_identity, operation="sealed ledger verification"
        )
        if ledger_identity != identity:
            raise StoreError(
                "custody receipt relabels the ledger store identity",
                ledger_identity=ledger_identity,
                receipt_identity=identity,
            )
        migration = self._migration_custody_projection(
            rows, meta, expected_store_identity=dict(identity)
        )
        expected = {
            "status": "sealed",
            "ledger_schema": CONCEPTRIC_DB_SCHEMA,
            "ledger_ref": self.path.name,
            "ledger_sha256": sha256_file(self.path),
            "event_count": len(rows),
            "head_digest": self._head_digest(rows),
            "event_hive_ref": meta.get("event_hive_ref"),
            "event_hive_codec": meta.get("event_hive_codec"),
            "reachability": reachability,
            "migration": migration,
            "authority_paths_root": self._custody_authority_paths_root(
                reachability, migration_present=bool(migration["present"])
            ),
            "claims": self._custody_claims(),
        }
        adoption_raw = meta.get(PORTABLE_AUTHORITY_ADOPTION_META_KEY)
        if adoption_raw is not None:
            try:
                adoption = self._validate_portable_authority_adoption(
                    json.loads(adoption_raw)
                )
            except (TypeError, ValueError) as exc:
                raise StoreError("custody adoption grant is malformed") from exc
            expected["portable_adoption_grant_root"] = adoption["grant_root"]
        failures = {
            key: {"expected": value, "got": receipt.get(key)}
            for key, value in expected.items()
            if canonical_json(receipt.get(key)) != canonical_json(value)
        }
        if failures:
            raise StoreError(
                "custody receipt disagrees with the current commit-shaped authority",
                path=str(self.custody_receipt_path),
                failures=failures,
            )
        return receipt

    def verify_custody(self) -> dict[str, Any]:
        """Verify ledger, WAL, hives and both receipts as one commit-shaped authority."""

        with self._locked(shared=True):
            return self._verify_custody_unlocked()

    def _seal_custody_unlocked(self, store_identity: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            self._refresh_schema(connection)
            if self.schema_version != CONCEPTRIC_DB_SCHEMA:
                raise StoreError(
                    "custody sealing requires a hived schema-v2 ledger",
                    schema=self.schema_version,
                )
            event_count = int(
                connection.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
            )
            if event_count == 0:
                raise StoreError(
                    "custody sealing refuses an empty authority",
                    event_count=event_count,
                )
            anchor_row = connection.execute(
                "SELECT value FROM meta WHERE key = 'store_role_anchor_json'"
            ).fetchone()
            if anchor_row is not None:
                try:
                    recorded_anchor = json.loads(str(anchor_row["value"]))
                except ValueError as exc:
                    raise StoreError("ledger store role anchor is malformed") from exc
                recorded_anchor = self._validate_store_identity(
                    recorded_anchor, operation="custody sealing role anchor"
                )
                if recorded_anchor != store_identity:
                    raise StoreError(
                        "custody sealing refuses to relabel an anchored store",
                        recorded=recorded_anchor,
                        requested=store_identity,
                    )
            identity_row = connection.execute(
                "SELECT value FROM meta WHERE key = 'store_identity_json'"
            ).fetchone()
            if identity_row is None:
                connection.execute(
                    "INSERT INTO meta(key, value) VALUES ('store_identity_json', ?)",
                    (canonical_json(store_identity),),
                )
                connection.commit()
            else:
                try:
                    recorded_identity = json.loads(str(identity_row["value"]))
                except ValueError as exc:
                    raise StoreError("ledger store identity is malformed") from exc
                if recorded_identity != store_identity:
                    raise StoreError(
                        "custody sealing refuses to relabel an established store",
                        recorded=recorded_identity,
                        requested=store_identity,
                    )
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.commit()
            rows = self._read_rows_from(connection)
            meta = self._meta_values(connection)
        self._refuse_uncheckpointed_authority()
        reachability = self._hive_reachability_unlocked()
        self._require_exact_reachability(reachability)
        migration = self._migration_custody_projection(
            rows, meta, expected_store_identity=store_identity
        )
        receipt = {
            "schema_version": HIVE_CUSTODY_RECEIPT_SCHEMA,
            "status": "sealed",
            "store_identity": store_identity,
            "ledger_schema": CONCEPTRIC_DB_SCHEMA,
            "ledger_ref": self.path.name,
            "ledger_sha256": sha256_file(self.path),
            "event_count": len(rows),
            "head_digest": self._head_digest(rows),
            "event_hive_ref": meta["event_hive_ref"],
            "event_hive_codec": meta["event_hive_codec"],
            "reachability": reachability,
            "migration": migration,
            "authority_paths_root": self._custody_authority_paths_root(
                reachability, migration_present=bool(migration["present"])
            ),
            "claims": self._custody_claims(),
        }
        adoption_raw = meta.get(PORTABLE_AUTHORITY_ADOPTION_META_KEY)
        if adoption_raw is not None:
            try:
                adoption = self._validate_portable_authority_adoption(
                    json.loads(adoption_raw)
                )
            except (TypeError, ValueError) as exc:
                raise StoreError("custody adoption grant is malformed") from exc
            receipt["portable_adoption_grant_root"] = adoption["grant_root"]
        write_atomic(
            self.custody_receipt_path,
            (canonical_json(receipt) + "\n").encode("utf-8"),
        )
        self._fsync_directory(self.root)
        return self._verify_custody_unlocked()

    def seal_custody(self, *, store_role: str) -> dict[str, Any]:
        """Checkpoint authority and mint the exact current custody proof.

        This is an explicit write act for a commit boundary, never an incidental read repair.
        """

        if self.read_only:
            raise StoreError("read-only conceptric store refuses custody sealing")
        store_role = store_role.strip()
        role_tokens = set(store_role.casefold().replace("_", "-").split("-"))
        if not store_role or role_tokens.intersection({"prod", "production"}):
            raise StoreError(
                "custody sealing requires a concrete non-production store role",
                store_role=store_role,
            )
        if self._expected_store_role is not None and store_role != self._expected_store_role:
            raise StoreError(
                "custody sealing role disagrees with the caller's authority anchor",
                expected_role=self._expected_store_role,
                got_role=store_role,
            )
        identity = {
            "schema_version": "atlas.store-identity/1",
            "role": store_role,
            "database_ref": self.path.name,
        }
        with self._locked():
            return self._seal_custody_unlocked(identity)

    def _replay_unlocked(self) -> ConceptricState:
        """Replay one ledger/projection pair while the caller owns the store lock."""

        with self._connect() as connection:
            self._refresh_schema(connection)
            rows = self._read_rows_from(connection)
            state = self._fold(rows)
        self._verify_or_reconstruct_projection(rows, state)
        return state

    def replay(self) -> ConceptricState:
        # The ledger and its disposable projection are two files committed in sequence.
        # A live writer may move from one to the other between two independent read snapshots;
        # without the shared store lock that transiently presents an ahead/behind projection as
        # corruption. Writers already hold this lock exclusively across BOTH commits. Read-only
        # faces hold it shared across both reads, so many readers coexist without seeing a torn pair.
        # A read-only face never repairs on disk and therefore shares the lock. A writable
        # face owns the exclusive lock because arbitrary poison in the disposable projection
        # is recovered automatically by atomic replacement inside `_replay_unlocked`.
        with self._locked(shared=self.read_only):
            return self._replay_unlocked()

    def replay_authority_only(self) -> ConceptricState:
        """Fold only the verified causal ledger and event hives.

        Runtime-custody snapshots outlive disposable projection schemas.  Verification of an
        immutable historical snapshot must therefore prove its authority without first asking a
        newer reader to understand (or repair) the snapshot's old projection tables.  This path
        deliberately performs no projection read, comparison, or reconstruction; ordinary
        operational readers should continue to use :meth:`replay`.
        """

        with self._locked(shared=True), self._connect() as connection:
            self._refresh_schema(connection)
            return self._fold(self._read_rows_from(connection))

    materialize = replay

    def current_state(self) -> ConceptricState:
        """Return the exact current fold, verifying only an unseen causal suffix when possible.

        This is the operational conjugate of ``replay`` for a long-lived writable process.
        Construction fully verifies history once; later cross-process drift joins through the
        compact ledger digest and inflates only the new event hives. Read-only faces use the same
        verified suffix under a shared lock but never inspect or repair the disposable projection;
        legacy v1 stores replay because they have no separate compact/hived suffix boundary.
        """

        with self._verified_cache_lock:
            with self._locked(shared=self.read_only), self._connect() as connection:
                self._refresh_schema(connection)
                if self.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA:
                    rows = self._read_v1_rows_from(connection)
                    self._prime_verified_head(rows)
                else:
                    self._refresh_verified_head_if_needed_locked(
                        connection, repair_projection=not self.read_only
                    )
                return self._verified_state

    def _object_kind_projection_locked(
        self,
        connection: sqlite3.Connection,
        *,
        kind: str,
    ) -> dict[str, Any]:
        """Read and verify one keyed object-kind frontier while the store lock is held.

        The graph projection is disposable, so every returned row is checked against its
        declaring hived ledger event.  The resulting frontier changes only when this object
        kind changes; unrelated Atlas traffic therefore does not create a false compare-and-
        swap conflict for a narrow append-only adapter.
        """

        if self.schema_version != CONCEPTRIC_DB_SCHEMA:
            raise StoreError("object-kind frontier requires the hived Atlas store")
        normalized_kind = str(kind).strip()
        if not normalized_kind:
            raise StoreError("object-kind frontier requires one exact kind")
        expected_meta = {
            "graph_projection_schema": GRAPH_PROJECTION_SCHEMA,
            "authoritative_head_digest": self._verified_head_digest,
            "projected_event_count": str(self._verified_sequence),
            "projected_head_event_id": self._verified_state.head_event_id or "",
        }
        try:
            with self._open_sqlite(self.projection_path, read_only=True) as projection:
                meta = {
                    str(row["key"]): str(row["value"])
                    for row in projection.execute(
                        "SELECT key, value FROM meta WHERE key IN "
                        "('graph_projection_schema', 'authoritative_head_digest', "
                        "'projected_event_count', 'projected_head_event_id')"
                    )
                }
                disagreements = {
                    key: {"expected": expected, "got": meta.get(key)}
                    for key, expected in expected_meta.items()
                    if meta.get(key) != expected
                }
                if disagreements:
                    raise HistoryChainMismatch(
                        "object-kind projection moved or is unavailable",
                        code="MOVED",
                        disagreements=disagreements,
                    )
                projected = tuple(
                    projection.execute(
                        "SELECT object_id, kind, content_handle, assumption, fibre, "
                        "grade_contract_id, grade_coordinate_json, declared_event_id, "
                        "object_json FROM objects WHERE kind = ? ORDER BY object_id",
                        (normalized_kind,),
                    )
                )
        except HistoryChainMismatch:
            raise
        except (sqlite3.Error, OSError) as exc:
            raise StoreError(
                "object-kind projection is unavailable",
                kind=normalized_kind,
                path=str(self.projection_path),
            ) from exc

        entries: list[dict[str, Any]] = []
        for row in projected:
            try:
                object_body = json.loads(str(row["object_json"]))
                item = ConceptricObject.from_dict(object_body)
            except (AtlasError, TypeError, ValueError) as exc:
                raise HistoryChainMismatch(
                    "object-kind projection row is unreadable",
                    code="DIRTY",
                    object_id=str(row["object_id"]),
                ) from exc
            column_facts = {
                "object_id": item.object_id,
                "kind": item.kind,
                "content_handle": item.content_handle,
                "assumption": item.assumption,
                "fibre": item.fibre,
                "grade_contract_id": item.grade_contract_id,
                "grade_coordinate_json": canonical_json(item.grade_coordinate),
            }
            column_disagreements = {
                key: {"expected": expected, "got": row[key]}
                for key, expected in column_facts.items()
                if row[key] != expected
            }
            if column_disagreements:
                raise HistoryChainMismatch(
                    "object-kind projection columns contradict their object",
                    code="DIRTY",
                    object_id=item.object_id,
                    disagreements=column_disagreements,
                )
            declared_raw = connection.execute(
                "SELECT sequence, previous_digest, record_digest, event_id, event_kind, "
                "assumption, fibre, event_handle FROM events WHERE event_id = ?",
                (str(row["declared_event_id"]),),
            ).fetchone()
            if declared_raw is None:
                raise HistoryChainMismatch(
                    "object-kind projection cites an absent declaration event",
                    code="DIRTY",
                    object_id=item.object_id,
                )
            declared = self._stored_v2_from_raw(declared_raw)
            if (
                declared.event.kind != EventKind.OBJECT
                or declared.event.payload != item.to_dict()
            ):
                raise HistoryChainMismatch(
                    "object-kind projection contradicts its declaring event",
                    code="DIRTY",
                    object_id=item.object_id,
                    declared_event_id=declared.event.event_id,
                )
            entries.append(
                {
                    "sequence": declared.sequence,
                    "record_digest": declared.record_digest,
                    "declared_event_id": declared.event.event_id,
                    "object": item.to_dict(),
                }
            )
        entries.sort(key=lambda row: (int(row["sequence"]), row["object"]["object_id"]))
        frontier_body = {
            "schema_version": "atlas.object-kind-frontier/1",
            "kind": normalized_kind,
            "entries": [
                {
                    "sequence": row["sequence"],
                    "record_digest": row["record_digest"],
                    "declared_event_id": row["declared_event_id"],
                    "object_id": row["object"]["object_id"],
                    "content_handle": row["object"]["content_handle"],
                }
                for row in entries
            ],
        }
        return {
            **frontier_body,
            "frontier_root": chash(frontier_body),
            "rows": entries,
            "read_metrics": {
                "projection_rows_loaded": len(projected),
                "declaration_rows_loaded": len(entries),
                "global_history_replayed": False,
            },
        }

    def read_object_kind_frontier(self, *, kind: str) -> dict[str, Any]:
        """Return one verified append-only object family without replaying Atlas history."""

        with self._verified_cache_lock:
            with self._locked(shared=True), self._connect() as connection:
                self._refresh_schema(connection)
                if self.schema_version != CONCEPTRIC_DB_SCHEMA:
                    raise StoreError("object-kind frontier requires the hived Atlas store")
                self._refresh_verified_head_if_needed_locked(
                    connection, repair_projection=False
                )
                return self._object_kind_projection_locked(connection, kind=kind)

    def append_many_if_object_kind_frontier(
        self,
        events: Iterable[AtlasEvent],
        *,
        kind: str,
        expected_frontier_root: str,
    ) -> tuple[StoredEvent, ...]:
        """Append iff one object family still equals the caller's verified read frontier.

        This is a narrow optimistic-concurrency primitive for immutable adapters.  It does not
        turn a caller-provided digest into authority: the root is rederived from verified
        projection rows and their hived declaration events under the same exclusive store lock
        that protects the append.
        """

        _refuse_test_write(self.root)
        packet = tuple(events)
        if not packet:
            return ()
        if self.read_only:
            raise StoreError("read-only conceptric store refuses append", path=str(self.path))
        normalized_kind = str(kind).strip()
        if not normalized_kind:
            raise StoreError("object-kind frontier CAS requires one exact kind")
        for event in packet:
            if event.kind != EventKind.OBJECT:
                raise StoreError(
                    "object-kind frontier CAS accepts OBJECT declarations only",
                    event_kind=event.kind.value,
                )
            try:
                item = ConceptricObject.from_dict(event.payload)
            except (AtlasError, TypeError, ValueError) as exc:
                raise StoreError(
                    "object-kind frontier CAS received an invalid object declaration"
                ) from exc
            if item.kind != normalized_kind:
                raise StoreError(
                    "object-kind frontier CAS event kind does not match its frontier",
                    expected_kind=normalized_kind,
                    object_kind=item.kind,
                )
        expected = str(expected_frontier_root).strip()
        if not expected.startswith(HASH_PREFIX):
            raise StoreError("object-kind frontier CAS requires one exact hash")
        with self._verified_cache_lock, self._locked(), self._connect() as connection:
            self._refresh_schema(connection)
            if self.schema_version != CONCEPTRIC_DB_SCHEMA:
                raise StoreError("object-kind frontier CAS requires the hived Atlas store")
            self._refresh_verified_head_if_needed_locked(
                connection, repair_projection=True
            )
            observed = self._object_kind_projection_locked(connection, kind=normalized_kind)
            if observed["frontier_root"] != expected:
                raise HistoryChainMismatch(
                    "object-kind frontier moved before append",
                    code="MOVED",
                    kind=normalized_kind,
                    expected_frontier_root=expected,
                    observed_frontier_root=observed["frontier_root"],
                )
            return self._append_many_v2(connection, packet)

    def append(self, event: AtlasEvent) -> StoredEvent:
        return self.append_many((event,))[0]

    @staticmethod
    def _refuse_new_legacy_seat_lifecycle(event: AtlasEvent) -> None:
        """Keep legacy payloads replayable while refusing their post-cutover creation."""

        if (
            event.kind == EventKind.SEAT_JOIN
            and event.payload.get("schema_version") != SeatJoinReceipt.SCHEMA_VERSION
        ):
            raise StateTransitionRefused(
                "new legacy seat joins are refused after the lifecycle cutover",
                schema_version=event.payload.get("schema_version"),
            )
        if (
            event.kind == EventKind.SEAT_OCCUPANCY_BINDING
            and event.payload.get("schema_version") != SeatOccupancyBinding.SCHEMA_VERSION
        ):
            raise StateTransitionRefused(
                "new legacy seat bindings are refused after the lifecycle cutover",
                schema_version=event.payload.get("schema_version"),
            )

    @staticmethod
    def _require_closed_lifecycle_packet(
        new_rows: list[tuple[StoredEvent, ConceptricState, ConceptricState]],
    ) -> None:
        """Every current join must bind, and any predecessor must retire, atomically."""

        for stored, before, _after in new_rows:
            event = stored.event
            if (
                event.kind != EventKind.SEAT_JOIN
                or event.payload.get("schema_version") != SeatJoinReceipt.SCHEMA_VERSION
            ):
                continue
            joined = SeatJoinReceipt.from_dict(event.payload)
            predecessor = before.seat_occupancies.get(joined.seat_id)
            expected_predecessor = (
                predecessor.binding_event_id
                if predecessor is not None and predecessor.routing_authority
                else None
            )
            matching = [
                later.event
                for later, _later_before, _later_after in new_rows
                if later.event.kind == EventKind.SEAT_OCCUPANCY_BINDING
                and later.event.payload.get("schema_version") == SeatOccupancyBinding.SCHEMA_VERSION
                and later.event.payload.get("join_event_id") == event.event_id
                and later.event.payload.get("predecessor_binding_event_id") == expected_predecessor
            ]
            if len(matching) != 1:
                raise StateTransitionRefused(
                    "current seat handover must close as one join-and-binding packet",
                    seat_id=joined.seat_id,
                    join_event_id=event.event_id,
                    expected_predecessor=expected_predecessor,
                    matching_binding_count=len(matching),
                )

    def _validate_packet(
        self, rows: tuple[StoredEvent, ...], packet: tuple[AtlasEvent, ...]
    ) -> tuple[list[StoredEvent], list[tuple[StoredEvent, ConceptricState, ConceptricState]]]:
        by_event_id = {row.event.event_id: row for row in rows}
        state = self._fold(rows)
        previous = self._head_digest(rows)
        stored_packet: list[StoredEvent] = []
        new_rows: list[tuple[StoredEvent, ConceptricState, ConceptricState]] = []
        saw_new = False
        packet_ids: set[str] = set()
        for event in packet:
            if event.event_id in packet_ids:
                raise StoreError("atomic event packet repeats an event id", event_id=event.event_id)
            packet_ids.add(event.event_id)
            existing = by_event_id.get(event.event_id)
            if existing is not None:
                if saw_new:
                    raise StoreError(
                        "atomic event retry interleaves stored and new events",
                        event_id=event.event_id,
                    )
                stored_packet.append(existing)
                continue
            saw_new = True
            self._refuse_new_legacy_seat_lifecycle(event)
            next_state = apply_event(state, event)
            stored = StoredEvent.create(len(rows) + len(new_rows) + 1, previous, event)
            stored_packet.append(stored)
            new_rows.append((stored, state, next_state))
            previous = stored.record_digest
            state = next_state
        self._require_closed_lifecycle_packet(new_rows)
        if new_rows:
            with self._connect() as index:
                self._require_current_owners(index, new_rows)
        return stored_packet, new_rows

    def _validate_v2_packet_from_head(
        self, connection: sqlite3.Connection, packet: tuple[AtlasEvent, ...]
    ) -> tuple[list[StoredEvent], list[tuple[StoredEvent, ConceptricState, ConceptricState]]]:
        """Validate a packet against the verified cached head, reading retries only.

        The compact event-id index answers idempotency. A retry still descends through and
        verifies its one hived event; a new event never reads a historical chunk. The cache is
        used only after `_refresh_verified_head_if_needed` matched it to the authoritative tip.
        """

        state = self._verified_state
        previous = self._verified_head_digest
        sequence = self._verified_sequence
        stored_packet: list[StoredEvent] = []
        new_rows: list[tuple[StoredEvent, ConceptricState, ConceptricState]] = []
        saw_new = False
        packet_ids: set[str] = set()
        for event in packet:
            if event.event_id in packet_ids:
                raise StoreError("atomic event packet repeats an event id", event_id=event.event_id)
            packet_ids.add(event.event_id)
            raw = connection.execute(
                "SELECT sequence, previous_digest, record_digest, event_id, event_kind, "
                "assumption, fibre, event_handle FROM events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            if raw is not None:
                if saw_new:
                    raise StoreError(
                        "atomic event retry interleaves stored and new events",
                        event_id=event.event_id,
                    )
                stored_packet.append(self._stored_v2_from_raw(raw))
                continue
            saw_new = True
            self._refuse_new_legacy_seat_lifecycle(event)
            next_state = apply_event(state, event)
            stored = StoredEvent.create(sequence + len(new_rows) + 1, previous, event)
            stored_packet.append(stored)
            new_rows.append((stored, state, next_state))
            previous = stored.record_digest
            state = next_state
        self._require_closed_lifecycle_packet(new_rows)
        if new_rows and any(row[0].event.kind == EventKind.REVISION for row in new_rows):
            if not self._projection_receipt_matches(expected_head=self._verified_head_digest):
                self._ensure_projection(self._read_v2_rows_from(connection))
            with self._open_sqlite(self.projection_path, read_only=True) as index:
                self._require_current_owners(index, new_rows)
        return stored_packet, new_rows

    @staticmethod
    def _require_current_owners(index, new_rows) -> None:
        """Refuse a revision packet that leaves a current containing node behind.

        Existing owners are found through the disposable graph's indexed DOWN edges.
        Only the packet's newly created nodes are inspected directly. Both object ids
        and content handles name the same obligation, across every assumption fibre.
        """
        revisions = [row[0].event for row in new_rows
                     if row[0].event.kind == EventKind.REVISION]
        if not revisions:
            return
        before, after = new_rows[0][1], new_rows[-1][2]
        superseded = {ref: tuple(event.payload["produces"])
                      for event in revisions for ref in event.payload["supersedes"]}
        retired = {ref for act in before.revision_acts.values() for ref in act.supersedes}
        obligations = set()
        for ref in superseded:
            rows = index.execute(
                "SELECT DISTINCT owner.object_id FROM objects child "
                "JOIN edges edge ON edge.target_object_id = child.object_id "
                "AND edge.relation = 'down-member-to' "
                "JOIN objects owner ON owner.object_id = edge.source_object_id "
                "WHERE child.object_id = ? OR child.content_handle = ?", (ref, ref))
            obligations.update(str(row[0]) for row in rows)
        for owner_id in obligations:
            owner = before.graph_objects.get(owner_id)
            if owner is None:
                raise HistoryChainMismatch("reverse member index cites an absent owner", object_id=owner_id)
            if owner_id in retired or owner.content_handle in retired:
                continue
            successors = superseded.get(owner_id) or superseded.get(owner.content_handle)
            if not successors:
                raise StaleOwner("publication must supersede every current member owner in the same packet",
                                 door="ConceptricStore.append_many", owner=owner_id,
                                 owner_handle=owner.content_handle)
            for ref in successors:
                resolved = after.graph_objects.get(ref)
                if resolved is None:
                    resolved = next((obj for obj in after.graph_objects.values()
                                     if obj.content_handle == ref and obj.kind == owner.kind), None)
                if resolved is None or resolved.kind != owner.kind or resolved.content_handle == owner.content_handle:
                    raise StaleOwner("owner replacement must resolve to a new containing node",
                                     owner=owner_id, successor=ref, door="ConceptricStore.append_many")
        # A packet must not mint a new stale owner while retiring the old one.
        changed_refs = set(superseded)
        for ref in superseded:
            obj = before.graph_objects.get(ref)
            if obj is not None:
                changed_refs.add(obj.content_handle)
        for oid in after.graph_objects.keys() - before.graph_objects.keys():
            obj = after.graph_objects[oid]
            if obj.kind == "coarse-node" and changed_refs.intersection(obj.attributes.get("member_handles", ())):
                raise StaleOwner("new owner still contains a superseded member", owner=oid,
                                 door="ConceptricStore.append_many")

    def _append_many_v1(
        self, connection: sqlite3.Connection, packet: tuple[AtlasEvent, ...]
    ) -> tuple[StoredEvent, ...]:
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = self._read_v1_rows_from(connection)
            stored_packet, new_rows = self._validate_packet(rows, packet)
            for stored, before, after in new_rows:
                self._insert_event_v1(connection, stored)
                self._project_delta(connection, before, after, stored.event.event_id)
            projected_head = self._head_digest(rows + tuple(item[0] for item in new_rows))
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('authoritative_head_digest', ?)",
                (projected_head,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES "
                "('development_review_head_digest', ?)",
                (projected_head,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('seat_mail_projection_schema', ?)",
                (SEAT_MAIL_PROJECTION_SCHEMA,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('seat_mail_head_digest', ?)",
                (projected_head,),
            )
            connection.commit()
            return tuple(stored_packet)
        except (sqlite3.Error, AtlasError) as exc:
            connection.rollback()
            if isinstance(exc, AtlasError):
                raise
            raise StoreError(
                "conceptric transaction failed", path=str(self.path), error=str(exc)
            ) from exc

    def _append_many_v2(
        self, connection: sqlite3.Connection, packet: tuple[AtlasEvent, ...]
    ) -> tuple[StoredEvent, ...]:
        self._refresh_verified_head_if_needed(connection)
        stored_packet, new_rows = self._validate_v2_packet_from_head(connection, packet)
        if not new_rows:
            return tuple(stored_packet)

        handles = [
            self.hive.put(canonical_json(item[0].event.to_dict()).encode()) for item in new_rows
        ]
        try:
            connection.execute("BEGIN IMMEDIATE")
            for (stored, _before, _after), handle in zip(new_rows, handles, strict=True):
                self._insert_event_v2(connection, stored, handle)
            checkpoint = self._checkpoint_for_state(
                new_rows[-1][2],
                head_record_digest=new_rows[-1][0].record_digest,
            )
            self._write_checkpoint(connection, checkpoint)
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('authoritative_head_digest', ?)",
                (new_rows[-1][0].record_digest,),
            )
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise StoreError(
                "compact conceptric ledger transaction failed",
                path=str(self.path),
                error=str(exc),
            ) from exc

        head = new_rows[-1][0].record_digest
        try:
            projection = self._connect_projection()
            try:
                with projection:
                    projection.execute("BEGIN IMMEDIATE")
                    for stored, before, after in new_rows:
                        self._project_delta(projection, before, after, stored.event.event_id)
                    projection.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES "
                        "('authoritative_head_digest', ?)",
                        (head,),
                    )
                    projection.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES "
                        "('development_review_projection_schema', ?)",
                        (DEVELOPMENT_REVIEW_PROJECTION_SCHEMA,),
                    )
                    projection.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES "
                        "('development_review_head_digest', ?)",
                        (head,),
                    )
                    projection.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES "
                        "('seat_mail_projection_schema', ?)",
                        (SEAT_MAIL_PROJECTION_SCHEMA,),
                    )
                    projection.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES "
                        "('seat_mail_head_digest', ?)",
                        (head,),
                    )
                    projection.commit()
            finally:
                # sqlite3.Connection's context manager commits or rolls back but does not close.
                # Close before returning so a later read-only constructor cannot trigger a
                # deferred projection checkpoint and be falsely blamed for mutating authority.
                projection.close()
        except (sqlite3.Error, AtlasError) as exc:
            # Authority already committed.  A derived-cache fault must not turn that success
            # into an ambiguous append failure: rebuild from the exact committed ledger while
            # this writer still owns the store lock.  Arbitrary path poison is quarantined by
            # `_replace_graph_projection`, never trusted or recursively deleted.
            try:
                self._replace_graph_projection(self._read_v2_rows_from(connection))
            except Exception as repair_exc:
                raise StoreError(
                    "ledger committed but disposable projection repair failed",
                    ledger_head=head,
                    projection=str(self.projection_path),
                    update_error=str(exc),
                    repair_error=str(repair_exc),
                ) from repair_exc
        self._verified_sequence = new_rows[-1][0].sequence
        self._verified_head_digest = head
        self._verified_state = new_rows[-1][2]
        return tuple(stored_packet)

    @staticmethod
    def _validate_seat_join_information_proof(
        body_store: BlobStore,
        event: AtlasEvent,
    ) -> None:
        """Bind a current typed join to the exact provider proof body it cites."""

        joined = SeatJoinReceipt.from_dict(event.payload)
        if event.payload.get("schema_version") != SeatJoinReceipt.SCHEMA_VERSION:
            return
        try:
            raw = json.loads(body_store.get(joined.information_proof_handle).decode("utf-8"))
        except (
            BlobMissing,
            BlobHashMismatch,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise StateTransitionRefused(
                "seat join information proof is unavailable or corrupt",
                information_proof_handle=joined.information_proof_handle,
            ) from exc
        if not isinstance(raw, Mapping):
            raise StateTransitionRefused("seat join information proof body must be an object")
        gate_mismatches = {
            "schema_version": (
                "laplace.startup-mail-gate/1",
                raw.get("schema_version"),
            ),
            "state": ("MAIL_READY", raw.get("state")),
            "seat_id": (joined.seat_id, raw.get("seat_id")),
        }
        gate_mismatches = {
            name: {"expected": expected, "got": got}
            for name, (expected, got) in gate_mismatches.items()
            if got != expected
        }
        if gate_mismatches:
            raise StateTransitionRefused(
                "seat join information proof contradicts the typed join",
                mismatches=gate_mismatches,
            )

        generation = joined.provider_identity_generation
        if generation is None:
            return
        identity = raw.get("provider_identity")
        if not isinstance(identity, Mapping):
            raise StateTransitionRefused(
                "typed watcher generation requires a provider identity proof body"
            )
        provider, separator, provider_task_id = joined.holder_ref.partition(":")
        expected_identity = {
            "schema_version": "laplace.provider-session-identity/1",
            "state": "VERIFIED",
            "provider_session_ref": joined.holder_ref,
            "provider": provider,
            "identity_kind": f"{provider}-thread-watcher-binding",
            "watcher_seat_id": joined.seat_id,
            "watcher_target_thread_id": provider_task_id,
            "watcher_lease_generation": generation,
        }
        mismatches = {
            name: {"expected": expected, "got": identity.get(name)}
            for name, expected in expected_identity.items()
            if identity.get(name) != expected
        }
        if not separator:
            mismatches["provider_session_ref"] = {
                "expected": "<provider>:<exact-task>",
                "got": joined.holder_ref,
            }
        if mismatches:
            raise StateTransitionRefused(
                "verified seat join provider identity proof contradicts the typed join",
                mismatches=mismatches,
            )

    @staticmethod
    def _validate_message_migration_supersession_evidence(
        body_store: BlobStore,
        event: AtlasEvent,
    ) -> None:
        """Refuse a migration act whose source-bearing authority cannot resolve at the door."""

        recovery = MessageMigrationSupersession.from_dict(event.payload)
        required_handles = {
            recovery.recovery_capsule_handle,
            recovery.author_turn_handle,
            recovery.authority_body_handle,
            recovery.operator_provider_identity_proof_handle,
        }
        provenance_digests = {source.digest for source in event.provenance}
        if not required_handles.issubset(provenance_digests):
            raise StateTransitionRefused(
                "message migration supersession provenance omits required custody",
                missing=sorted(required_handles - provenance_digests),
            )
        try:
            body_store.get(recovery.recovery_capsule_handle)
            authority_body = body_store.get(recovery.authority_body_handle)
            author_turn_bytes = body_store.get(recovery.author_turn_handle)
            provider_proof_bytes = body_store.get(recovery.operator_provider_identity_proof_handle)
            author_turn = json.loads(author_turn_bytes.decode("utf-8"))
            provider_proof = json.loads(provider_proof_bytes.decode("utf-8"))
        except (
            BlobMissing,
            BlobHashMismatch,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise StateTransitionRefused(
                "message migration supersession evidence is unavailable or corrupt"
            ) from exc

        if (
            not isinstance(provider_proof, Mapping)
            or provider_proof.get("schema_version") != "laplace.provider-session-identity/1"
            or provider_proof.get("state") != "VERIFIED"
            or provider_proof.get("provider_session_ref") != recovery.operator_provider_session_ref
            or provider_proof.get("watcher_seat_id") != recovery.operator_seat_id
            or provider_proof.get("watcher_lease_generation")
            != recovery.operator_provider_identity_generation
        ):
            raise StateTransitionRefused(
                "message migration supersession provider proof contradicts its operator"
            )
        if (
            not isinstance(author_turn, Mapping)
            or set(author_turn) != {"schema_version", "row"}
            or author_turn.get("schema_version") != "laplace.author-turn/1"
            or canonical_json(author_turn).encode("utf-8") != author_turn_bytes
        ):
            raise StateTransitionRefused(
                "message migration supersession author turn is not canonical custody"
            )
        row = author_turn.get("row")
        recipients = row.get("recipient_seat_ids") if isinstance(row, Mapping) else None
        if (
            not isinstance(row, Mapping)
            or row.get("schema_version") != "laplace.author-turn/1"
            or row.get("record") != "talk"
            or row.get("actor") != "gerard"
            or row.get("via") != "front-door"
            or not isinstance(recipients, list)
            or recovery.operator_seat_id not in recipients
        ):
            raise StateTransitionRefused(
                "message migration supersession lacks a Gerard front-door turn to its operator"
            )
        text = row.get("text")
        if not isinstance(text, str) or authority_body != text.encode("utf-8"):
            raise StateTransitionRefused(
                "message migration supersession authority body contradicts its author turn"
            )
        try:
            commission = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StateTransitionRefused(
                "message migration supersession author turn is not a commission object"
            ) from exc
        if (
            not isinstance(commission, Mapping)
            or canonical_json(commission) != text
            or dict(commission) != recovery.commission_dict()
            or chash(commission) != recovery.commission_handle
        ):
            raise StateTransitionRefused(
                "message migration supersession author turn names a different recovery coordinate"
            )

    def append_many(self, events: Iterable[AtlasEvent]) -> tuple[StoredEvent, ...]:
        """Validate and append a complete causal packet through the canonical write door."""
        _refuse_test_write(self.root)

        packet = tuple(events)
        if not packet:
            return ()
        if self.read_only:
            raise StoreError("read-only conceptric store refuses append", path=str(self.path))
        # A message envelope is not authoritative unless the exact body it names is already in
        # this store's provider custody.  State folding remains pure; the store write door owns
        # the existence/hash check because it alone has both the event and the bound authority
        # root. Direct append callers therefore cannot bypass the host send preflight.
        body_store = BlobStore(self.root / "blobs")
        for event in packet:
            if event.kind.value == "seat.message-sent":
                handle = event.payload.get("body_handle")
                if isinstance(handle, str) and handle:
                    body_store.get(handle)
            elif event.kind.value == "seat.joined":
                self._validate_seat_join_information_proof(body_store, event)
            elif event.kind == EventKind.MESSAGE_MIGRATION_SUPERSESSION:
                self._validate_message_migration_supersession_evidence(body_store, event)
            elif event.kind == EventKind.REGION_PUBLICATION_PREPARED:
                required = {
                    str(event.payload.get("patch_handle") or ""),
                    str(event.payload.get("custody_handle") or ""),
                }
                if "" in required:
                    raise StateTransitionRefused(
                        "publication prepare omits patch or custody handle"
                    )
                for handle in required:
                    body_store.get(handle)
                provenance = {source.digest for source in event.provenance}
                if not required.issubset(provenance):
                    raise StateTransitionRefused(
                        "publication prepare provenance omits exact custody",
                        missing=sorted(required - provenance),
                    )
        with self._verified_cache_lock, self._locked(), self._connect() as connection:
            self._refresh_schema(connection)
            if self.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA:
                return self._append_many_v1(connection, packet)
            return self._append_many_v2(connection, packet)

    def finalize_region_publication(
        self,
        events: Iterable[AtlasEvent],
        *,
        ref_cas: Callable[[], Any],
    ) -> tuple[StoredEvent, ...]:
        """Prevalidate FINALIZED+CHECKIN, perform one ref CAS, then append atomically.

        The exclusive Atlas lock spans the dry fold, the external compare-and-swap and the
        two-event transaction. A crash after Git moves but before SQLite commits is recovered by
        replaying the same keyed saga: ``ref_cas`` must accept the exact candidate as already
        applied, while any third ref value refuses.
        """

        _refuse_test_write(self.root)
        packet = tuple(events)
        if (
            len(packet) != 2
            or packet[0].kind != EventKind.REGION_PUBLICATION_FINALIZED
            or packet[1].kind != EventKind.REGION_CHECKIN
        ):
            raise StoreError("publication finalize requires FINALIZED+CHECKIN exactly")
        if self.read_only:
            raise StoreError("read-only conceptric store refuses publication finalize")
        with self._verified_cache_lock, self._locked(), self._connect() as connection:
            self._refresh_schema(connection)
            if self.schema_version != CONCEPTRIC_DB_SCHEMA:
                raise StoreError("publication finalize requires the hived authority ledger")
            self._refresh_verified_head_if_needed(connection)
            _stored, new_rows = self._validate_v2_packet_from_head(connection, packet)
            if len(new_rows) != 2:
                raise HistoryChainMismatch(
                    "publication finalize packet is partially present or already consumed"
                )
            ref_cas()
            return self._append_many_v2(connection, packet)

    @staticmethod
    def _temporary_database(root: Path, stem: str) -> Path:
        fd, raw_path = tempfile.mkstemp(prefix=f".{stem}-", suffix=".sqlite3", dir=root)
        os.close(fd)
        path = Path(raw_path)
        path.unlink()
        return path

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        _fsync_directory(path)

    def migrate_hived(
        self,
        *,
        store_role: str,
        hive_root: Path | None = None,
        retain_v1_receipt: bool = False,
    ) -> dict[str, Any]:
        """Explicitly migrate a schema-v1 store without repouring or changing event identity.

        The operation is refusal-safe: exact event chunks and fully verified candidate databases
        are built before the authoritative filename moves.  ``conceptric.sqlite3`` is atomically
        replaced under the same lock used by ``append``; a concurrent fabric writer therefore
        either commits before migration or waits and requires explicit v2 authority adoption.
        The old
        database can be retained as a hard-linked receipt when custody policy requires it.

        ``store_role`` is mandatory because a blueprint generation and the live runtime fabric are
        independent authorities even when both use this schema.  The vague role ``production`` is
        refused: it previously let evidence about the repourable blueprint appear to cover the
        separate runtime store carrying seat mail.
        """

        if self.read_only:
            raise StoreError("read-only conceptric store refuses migration", path=str(self.path))
        store_role = store_role.strip()
        role_tokens = set(store_role.casefold().replace("_", "-").split("-"))
        if not store_role or role_tokens.intersection({"prod", "production"}):
            raise StoreError(
                "migration requires a concrete non-production store role",
                store_role=store_role,
                examples=("blueprint-generation", "live-runtime-fabric", "test-fixture"),
            )
        if self._expected_store_role is not None and store_role != self._expected_store_role:
            raise StoreError(
                "migration role disagrees with the caller's authority anchor",
                expected_role=self._expected_store_role,
                got_role=store_role,
            )
        store_identity = {
            "schema_version": "atlas.store-identity/1",
            "role": store_role,
            "database_ref": self.path.name,
        }
        target_hive = (
            Path(hive_root) if hive_root is not None else self.root / DEFAULT_EVENT_HIVE_REF
        )
        target = CompressedHive(target_hive)
        ledger_candidate: Path | None = None
        projection_candidate: Path | None = None
        with self._locked():
            try:
                with self._connect() as source:
                    self._refresh_schema(source)
                    if self.schema_version == CONCEPTRIC_DB_SCHEMA:
                        if (
                            hive_root is not None
                            and Path(hive_root).resolve() != self.hive_root.resolve()
                        ):
                            raise StoreError(
                                "requested migration hive disagrees with migrated ledger",
                                requested=str(hive_root),
                                recorded=str(self.hive_root),
                            )
                        rows = self._read_v2_rows_from(source)
                        return {
                            "schema_version": CONCEPTRIC_DB_SCHEMA,
                            "status": "already-hived",
                            "store_identity": store_identity,
                            "event_count": len(rows),
                            "head_digest": self._head_digest(rows),
                            "hive_root": str(self.hive_root),
                        }
                    rows = self._read_v1_rows_from(source)
                    state = self._fold(rows)
                    source_meta = {
                        row["key"]: row["value"]
                        for row in source.execute("SELECT key, value FROM meta ORDER BY key")
                    }
                    source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                source_digest = sha256_file(self.path)
                source_meta_root = chash(
                    {
                        "schema_version": "atlas.conceptric-v1-meta/1",
                        "meta": source_meta,
                    }
                )
                source_event_chain_root = self._event_prefix_root(rows)
                handles = [target.put(canonical_json(row.event.to_dict()).encode()) for row in rows]
                hive_ref = self._hive_ref(self.root, target_hive)

                ledger_candidate = self._temporary_database(self.root, "conceptric-v2")
                with self._open_sqlite(ledger_candidate, wal=False) as candidate:
                    self._create_v2_schema(candidate, hive_ref=hive_ref)
                    # Storage migration does not adopt a writer context. Leave the explicit
                    # no-checkpoint state; an empty singleton table means corruption to the
                    # adoption verifier and cannot serve as a migration result.
                    candidate.execute("DROP TABLE authority_checkpoint")
                    candidate.commit()
                    candidate.execute("BEGIN IMMEDIATE")
                    for key, value in source_meta.items():
                        if key not in {
                            "schema_version",
                            "graph_projection_schema",
                            "authoritative_head_digest",
                        }:
                            candidate.execute(
                                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                                (key, value),
                            )
                    for stored, handle in zip(rows, handles, strict=True):
                        self._insert_event_v2(candidate, stored, handle)
                    candidate.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES "
                        "('authoritative_head_digest', ?)",
                        (self._head_digest(rows),),
                    )
                    candidate.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES "
                        "('migration_source_sha256', ?)",
                        (source_digest,),
                    )
                    candidate.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES "
                        "('migration_event_count', ?)",
                        (str(len(rows)),),
                    )
                    candidate.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES "
                        "('migration_source_meta_root', ?)",
                        (source_meta_root,),
                    )
                    candidate.commit()

                old_hive = self.hive
                old_hive_root = self.hive_root
                self.hive = target
                self.hive_root = target_hive
                try:
                    with self._open_sqlite(ledger_candidate, wal=False) as candidate:
                        candidate_rows = self._read_v2_rows_from(candidate)
                    if candidate_rows != rows:
                        raise HistoryChainMismatch(
                            "hived migration candidate changes canonical event history"
                        )

                    projection_candidate = self._temporary_database(
                        self.root, "conceptric-index-v2"
                    )
                    with self._open_sqlite(projection_candidate, wal=False) as projection:
                        self._create_projection_schema(projection)
                        projection.commit()
                        self._rebuild_graph_projection(
                            projection, rows, projection_schema=GRAPH_PROJECTION_SCHEMA
                        )
                        self._verify_graph_projection(projection, state, rows)
                except Exception:
                    self.hive = old_hive
                    self.hive_root = old_hive_root
                    raise

                backup_path = self.root / "conceptric.v1.sqlite3"
                if retain_v1_receipt:
                    if backup_path.exists():
                        if sha256_file(backup_path) != source_digest:
                            raise StoreError(
                                "v1 receipt path already contains different bytes",
                                path=str(backup_path),
                            )
                    else:
                        os.link(self.path, backup_path)

                if self.projection_path.exists():
                    with self._connect_projection() as projection:
                        projection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                # The candidate is a different SQLite database generation.  A checkpointed
                # v1 WAL/SHM pair is no longer authoritative, but leaving those canonical
                # sidecar names beside the replacement lets SQLite open the v2 inode through
                # v1 coordination bytes.  That exact seam produced a transient
                # ``database disk image is malformed`` while sealing the live Fabric migration.
                # Quarantine rather than delete: the old database is retained above and the
                # sidecars remain inspectable evidence if either checkpoint implementation
                # ever violates its contract.
                for suffix in ("-wal", "-shm"):
                    self._retire_disposable_obstruction(
                        self.path.with_name(self.path.name + suffix)
                    )
                os.replace(ledger_candidate, self.path)
                ledger_candidate = None
                os.replace(projection_candidate, self.projection_path)
                projection_candidate = None
                self._fsync_directory(self.root)

                self.schema_version = CONCEPTRIC_DB_SCHEMA
                self._prime_verified_head(rows)
                reachability = self._hive_reachability_unlocked()
                receipt = {
                    "schema_version": HIVE_MIGRATION_RECEIPT_SCHEMA,
                    "status": "migrated",
                    "store_identity": store_identity,
                    "source_schema": LEGACY_CONCEPTRIC_DB_SCHEMA,
                    "target_schema": CONCEPTRIC_DB_SCHEMA,
                    "source_database_sha256": source_digest,
                    "source_meta_root": source_meta_root,
                    "source_event_chain_root": source_event_chain_root,
                    "event_count": len(rows),
                    "head_digest": self._head_digest(rows),
                    "event_hive_ref": hive_ref,
                    "event_hive_codec": CompressedHive.codec,
                    "reachability": reachability,
                    "retained_v1_database": str(backup_path) if retain_v1_receipt else None,
                    "authorization_scope": {
                        "authorizing_fields": (
                            "store_identity",
                            "status",
                            "source_schema",
                            "target_schema",
                            "source_event_chain_root",
                            "event_count",
                            "head_digest",
                            "event_hive_ref",
                            "event_hive_codec",
                            "reachability",
                        ),
                        "historical_source_measurements": (
                            "source_database_sha256",
                            "source_meta_root",
                        ),
                        "storage_and_wall_clock_measurements": "absent-non-authorizing",
                    },
                }
                write_atomic(
                    self.migration_receipt_path,
                    (canonical_json(receipt) + "\n").encode("utf-8"),
                )
                # Migration is the first commit boundary for a hived store.  The historical
                # receipt proves the v1→v2 prefix; the current seal proves the exact ledger/WAL/
                # hive set that must travel now.  Later appends make this seal stale until the
                # next explicit commit boundary rather than silently rewriting history.
                self._seal_custody_unlocked(store_identity)
                # migrate_hived owns the exclusive store lock across this whole replacement;
                # acquiring a second flock from the same process can deadlock on Linux.
                if self._replay_unlocked() != state:
                    raise HistoryChainMismatch(
                        "hived store replay differs after authoritative replacement"
                    )
                return receipt
            finally:
                for candidate in (ledger_candidate, projection_candidate):
                    if candidate is not None and candidate.exists():
                        candidate.unlink()

    @classmethod
    def recover_incomplete_hived_migration(
        cls,
        root: Path,
        *,
        store_role: str,
    ) -> dict[str, Any]:
        """Seal an exactly verified v2 migration that stopped after the atomic swap.

        This is deliberately not a generic "ignore missing receipt" switch.  Writable
        construction continues to refuse a ledger identity whose custody receipt vanished.
        Recovery is a named act over the narrow migration seam: the v2 causal prefix, its
        migration receipt, zero-orphan hive reachability, store identity and retained v1
        database digest must all agree before the only missing artifact is minted.
        """

        role = store_role.strip()
        role_tokens = set(role.casefold().replace("_", "-").split("-"))
        if not role or role_tokens.intersection({"prod", "production"}):
            raise StoreError(
                "incomplete migration recovery requires a concrete non-production store role",
                store_role=store_role,
            )
        identity = {
            "schema_version": "atlas.store-identity/1",
            "role": role,
            "database_ref": "conceptric.sqlite3",
        }
        # Inspect the replacement main database without consulting any adjacent WAL.  The
        # failure this recovery exists for occurs after replacing the v1 inode: SQLite sidecars
        # can therefore belong to the old generation even though their canonical filenames now
        # sit beside v2.  The migration receipt below, rather than an unsealed ledger identity,
        # binds the requested role during this narrow recovery act.
        store = cls(Path(root), read_only=True, immutable=True)
        if store.custody_receipt_path.is_file():
            return cls(
                Path(root),
                read_only=True,
                expected_store_role=role,
            ).verify_custody()
        if store.schema_version != CONCEPTRIC_DB_SCHEMA:
            raise StoreError(
                "incomplete migration recovery requires the verified v2 replacement",
                schema=store.schema_version,
            )

        with store._locked():
            with store._connect() as connection:
                rows = store._read_v2_rows_from(connection)
                meta = store._meta_values(connection)
            migration = store._migration_custody_projection(
                rows,
                meta,
                expected_store_identity=identity,
            )
            if not migration.get("present"):
                raise StoreError("incomplete migration recovery requires a migration receipt")
            reachability = store._hive_reachability_unlocked()
            store._require_exact_reachability(reachability)

            receipt = store._read_receipt(
                store.migration_receipt_path,
                schema=HIVE_MIGRATION_RECEIPT_SCHEMA,
            )
            retained_raw = receipt.get("retained_v1_database")
            if not isinstance(retained_raw, str) or not retained_raw.strip():
                raise StoreError("incomplete migration recovery requires the retained v1 database")
            retained = Path(retained_raw)
            expected_retained = store.root / "conceptric.v1.sqlite3"
            if retained.resolve() != expected_retained.resolve() or not retained.is_file():
                raise StoreError(
                    "migration receipt does not name the exact retained v1 database",
                    retained=str(retained),
                    expected=str(expected_retained),
                )
            expected_digest = receipt.get("source_database_sha256")
            actual_digest = sha256_file(retained)
            if actual_digest != expected_digest:
                raise StoreError(
                    "retained v1 database disagrees with the migration source digest",
                    expected=expected_digest,
                    got=actual_digest,
                )

            # No ordinary writer can enter while custody is absent.  Consequently, once the
            # immutable v2 main, its complete causal prefix, hives, migration receipt and retained
            # v1 digest all agree, an adjacent WAL can contain only (a) residue from the replaced
            # v1 inode or (b) the interrupted sealer's recreatable store-identity frame.  Retire
            # both sidecars as evidence; the sealer below writes that identity against v2 afresh.
            for suffix in ("-wal", "-shm"):
                store._retire_disposable_obstruction(store.path.with_name(store.path.name + suffix))

            # The read-only constructor was intentionally admitted without writer repair.
            # Only after every migration authority check above may this exact instance open
            # the ledger for the missing seal; ordinary writer construction remains refused.
            store.read_only = False
            store.immutable = False
            try:
                sealed = store._seal_custody_unlocked(identity)
            finally:
                store.read_only = True
            return sealed

    def provider_snapshot(self, *, observed_at: str | None = None) -> dict[str, Any]:
        return self.current_state().provider_snapshot(observed_at=observed_at)

    def message_status(self, message_id: str) -> dict[str, Any] | None:
        record = self.current_state().messages.get(message_id)
        return None if record is None else record.to_dict()

    def pending_messages(
        self, seat_id: str, *, after_cursor: int, as_of: str
    ) -> tuple[dict[str, Any], ...]:
        return tuple(
            message.to_dict()
            for message in self.current_state().pending_messages(
                seat_id, after_cursor=after_cursor, as_of=as_of
            )
        )
