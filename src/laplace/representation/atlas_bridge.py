"""The legacy Fabric bridge from Laplace into the canonical Atlas (one of the two reviewed import boundaries).

It constructs typed Atlas events and appends them through ``ConceptricStore.append``.  Message bytes live in
Atlas's content-addressed blob store; cursor, delivery, lifecycle, assumption-fibre and permission truth all
remain derived from the one event history.  There is no bridge-side journal or status cache.

The declared runtime selects Atlas: the source tree supplies ``src/atlas`` beside this package, and the
portable installation supplies the separate ``atlas`` wheel built from that same source. This module adds no
path of its own: a missing, broken or namespace-only selected package refuses at the import below and is never
masked by a different source tree (core consolidation R2, 2026-10-19). This file is not thin: it is the legacy
Fabric bridge (store/custody, runtime custody capsule and recovery, leases/publication/provider authority,
context/message/permission/watcher adapters). Writing body custody does not need it: it reaches Atlas through
``laplace.representation.writing_representation``, the second reviewed import boundary (``tests/test_atlas_seal.py``).
"""

from __future__ import annotations
from laplace.core.checkout import repo_root

import base64
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from laplace.engine.telemetry import state_dir

REPO_ROOT = repo_root()
EXTRA_AUTHORITY_FILES: tuple[Path, ...] = (Path(__file__).resolve(),)

from atlas.errors import (  # noqa: E402
    AtlasError,
    BlobHashMismatch,
    BlobMissing,
    HistoryChainMismatch,
    StateTransitionRefused,
    StoreError,
    StoreLockTimeout,
)
from atlas.history import (  # noqa: E402
    AcknowledgementDisposition,
    ActPhase,
    AssumptionSelection,
    AtlasEvent,
    BootstrapCrutch,
    BoundaryRef,
    ConceptricObject,
    CorpusAct,
    EventKind,
    GradeAxis,
    LeaseCheckinOutcome,
    LeaseDeclarationKind,
    LifecycleAction,
    LifecyclePhase,
    LifecycleTransition,
    MaterializedReconstruction,
    MessageAcknowledgement,
    MessageExpiry,
    MessageForkPreservation,
    MessageMigrationSupersession,
    MessagePull,
    MessageSupersession,
    MoveDirection,
    Movement,
    PermissionDecision,
    PermissionOutcome,
    PermissionRequest,
    ProducerRef,
    RegionCheckin,
    RegionCheckout,
    RegionForwardClosure,
    RegionPublicationAuthorization,
    RegionPublicationFinalized,
    RegionPublicationPrepared,
    RegionPublicationSignoff,
    ReplEvaluation,
    ReplOperation,
    Residual,
    ResidualStatus,
    RuntimeReceipt,
    SeatAction,
    SeatJoinReceipt,
    SeatMessage,
    SeatOccupancyBinding,
    SeatRole,
    SeatStatus,
    SeatTransition,
    SourceRef,
    TransportReceipt,
    Validity,
    WatchCheckpoint,
    WatcherRegistration,
    WatchSourceKind,
    WatchStatus,
    region_forward_closure_consumption_root,
    region_forward_closure_finalized_projection,
    region_publication_affected_frontier_root,
    validate_authority_region,
)
from atlas.ids import canonical_json, chash, hash_bytes  # noqa: E402
from atlas.migration import (  # noqa: E402, F401 - exported through the one bridge
    MigrationEventContext,
    MigrationLedger,
    replay_migration,
)
from atlas.runtime import collect_runtime_receipt  # noqa: E402
from atlas.cards import compute_registry as compute_cards_registry  # noqa: E402, F401 - the verbs and structure cards, through the one bridge
from atlas.state import (  # noqa: E402
    CONTROL_AXIS_CONTRACT,
    MESSAGE_MIGRATION_RECOVERY_CAPSULE_HANDLE,
    PRESERVE_FORK_AUTHOR_RULING_REF,
    PRESERVE_FORK_AUTHORITY_EVENT_ID,
    PRESERVE_FORK_TARGET_MESSAGE_ID,
    ConceptricState,
    bootstrap_crutch_retirement,
    derive_message_migration_recovery_entries,
    effective_region_lease_projection,
)
from atlas.store import (  # noqa: E402
    CONCEPTRIC_DB_SCHEMA,
    LEGACY_CONCEPTRIC_DB_SCHEMA,
    LEGACY_UNTYPED_REVIEW_DECISIONS,
    LEGACY_UNTYPED_REVIEW_VERDICT_IDS,
    BlobStore,
    CompressedHive,
    ConceptricStore,
    StoredEvent,
    write_atomic,
)

from atlas.updown import ChildLeaf, CoarseNode, SpectralFrame, UpInputs, down, up  # noqa: E402, F401
from atlas.updown_history import UpActReceipt, bind_up_result  # noqa: E402, F401

BRIDGE_SCHEMA = "laplace.atlas-seat-bridge.v1"
BODY_MEDIA_TYPE = "text/plain; charset=utf-8"
_DEPENDENCY_FRESHNESS_ROOT = "__laplace_dependency_freshness_v1__"
_GIT_ROOT_NAMES = frozenset({"git_head", "repo_head"})
_FOLD_ROOT_NAMES = frozenset({"fold_head", "semantic_fold_head"})
_COORDINATE_ROOT_NAMES = frozenset({"coordinate_payload", "recovery_coordinate_payload"})
_ATLAS_CURSOR_ROOT_NAMES = frozenset({"atlas_cursor", "runtime_atlas_cursor"})
_ATLAS_HEAD_ROOT_NAMES = frozenset({"atlas_head_event_id", "runtime_atlas_head_event_id"})
_BLUEPRINT_ROOT_NAMES = frozenset({"blueprint_generation"})

# The stage-zero cutover has one expired, already-custodied consolidation envelope.  Its
# successor is deliberately a closed coordinate rather than a general-purpose copy command:
# live recovery must not ask an operator to transcribe body bytes, source roots, identity, or
# expiry from a historical row.  These constants are migration evidence and can be retired only
# after the v1 -> v2 recovery is durably closed.
STAGE_ZERO_STALE_REPLACEMENT_MESSAGE_ID = (
    "message:d0417206217235cf9f5357ba0a8aecf31914d9c00847953a7a99b954fdb1fb4f"
)
STAGE_ZERO_STALE_REPLACEMENT_BODY_HANDLE = (
    "sha256:de7b74e855be9da26c6c6cf4565a5b2c583611d5bfc83e4c7abd6a94540f2d56"
)
STAGE_ZERO_REISSUE_IDEMPOTENCY_KEY = "stage-zero:v2-reissue:d041:1"
STAGE_ZERO_REISSUE_EXPIRES_AT = "2026-09-03T00:00:00Z"
STAGE_ZERO_REISSUE_MESSAGE_ID = (
    "message:8929db65305f1a5ee3b334758cd41e61a6d732856158da15657da2715af69f38"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def store_root() -> Path:
    """Return the one durable Atlas root shared by every provider process."""

    return state_dir() / "atlas" / "conceptric"


def _authority_epoch_context(root: Path | None = None) -> dict[str, str]:
    """Use the store-owned per-file manifest for every live reader and writer."""

    return ConceptricStore.authority_context_manifest(
        root or store_root(), store_role="live-runtime-fabric",
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )


@lru_cache(maxsize=8)
def _store_at(root: str) -> ConceptricStore:
    """One verified store head per process/root; external tip drift refreshes inside append."""

    return ConceptricStore(
        Path(root),
        expected_store_role="live-runtime-fabric",
        authority_context=_authority_epoch_context(Path(root)),
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )


@lru_cache(maxsize=8)
def _read_store_at(root: str) -> ConceptricStore:
    """A no-transition store face: SQLite mode=ro plus bounded shared flock."""
    return ConceptricStore(
        Path(root),
        read_only=True,
        expected_store_role="live-runtime-fabric",
        authority_context=_authority_epoch_context(Path(root)),
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )


#: the one durable root, resolved WITHOUT LAPLACE_STATE — the store a test must never
#: be able to reach. Computed once at import so a mid-test env flip cannot move it.
_LIVE_ROOT = Path("~/.mcp-gerard/laplace").expanduser() / "atlas" / "conceptric"


class LiveStoreUnderTest(RuntimeError):
    """A test process tried to WRITE to the live Atlas fabric."""


def _refuse_live_write_under_test(root: Path) -> None:
    """STOP THE PRODUCER (superego, fabric #987, item a).

    Measured, not inferred: three author-act events — cursors 929/960/961, all
    interface-seat -> ego-seat — were appended to the AUTHORITATIVE ledger by pytest,
    citing WALKRED rows that exist nowhere (grep -c -> 0) and carrying body handles that
    do not resolve. They reconstruct byte-exactly from one test literal, "the composer is
    cramped", at tests/test_front_door.py:895. Events asserting THE AUTHOR ACTED were
    being forged into the authority, once per suite run.

    THE MECHANISM is a two-root split, not a race: /front/walked dispatches its notice on
    a DAEMON THREAD; by the time that thread runs, pytest's monkeypatch is torn down, so
    _blobs() resolves LAPLACE_STATE fresh into a dead tmp dir while append() reaches the
    live store through an lru_cached handle. Body and event land in different stores.

    THIS IS THE THIRD ATTEMPT AT THIS DEFECT AND THE FIRST STRUCTURAL ONE. 6be772d5 fixed
    the RECEIPT bank by capturing the root at dispatch; I guarded the selftest bank with
    the same trick an hour ago. Both are per-caller, and the superego's point stands: the
    organ is always already built, wired to one caller, never generalised, and the defect
    recurs one layer down. So the gate goes at the WRITE DOOR, where every caller — every
    present one and every future one — must pass. A test may write to any store it likes
    except the one the engine actually lives in.
    """
    if os.environ.get("LAPLACE_TEST_PROCESS") != "1":
        return
    try:
        same = root.resolve() == _LIVE_ROOT.resolve()
    except OSError:
        same = str(root) == str(_LIVE_ROOT)
    if same:
        raise LiveStoreUnderTest(
            "a test tried to write to the live Atlas fabric at "
            f"{_LIVE_ROOT} — refused at the write door. If this fires in your test, the "
            "store root was resolved after a monkeypatch was torn down (typically from a "
            "daemon thread); capture the root before dispatch or keep the work on-thread."
        )


def _store() -> ConceptricStore:
    root = store_root().resolve()
    _refuse_live_write_under_test(root)
    return _store_at(str(root))


def _read_store() -> ConceptricStore:
    return _read_store_at(str(store_root().resolve()))


def _blobs() -> BlobStore:
    return BlobStore(store_root() / "blobs")


def put_custody(data: bytes) -> str:
    """Bank exact bytes in Atlas custody and return their content handle.

    This is deliberately narrower than an event append: callers that mint a digest which another
    seat must descend through use this door first, then cite the returned resolvable handle from
    the typed event/materialization they own.
    """

    return _blobs().put(bytes(data))


def custody_has(handle: str) -> bool:
    """Answer whether an exact content handle is locally resolvable without reading its bytes."""

    return _blobs().has(handle)


def custody_body(*, handle: str) -> dict[str, Any]:
    """Resolve exact Atlas custody bytes without making a delivery or evaluation claim."""

    data = _blobs().get(handle)
    try:
        text: str | None = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return {
        "schema_version": "laplace.atlas-custody-body/1",
        "content_handle": handle,
        "media_type": "text/plain; charset=utf-8"
        if text is not None
        else "application/octet-stream",
        "text": text,
        "base64": None if text is not None else base64.b64encode(data).decode("ascii"),
        "bytes": len(data),
        "store": str(store_root() / "blobs"),
        "read_only": True,
        "transition_claim": "none",
    }


LEGACY_RUNTIME_CUSTODY_SCHEMA = "laplace.runtime-atlas-custody/1"
RUNTIME_CUSTODY_SCHEMA = "laplace.runtime-atlas-custody/2"
RUNTIME_RECOVERY_POINT_SCHEMA = "laplace.runtime-recovery-point/1"
RUNTIME_ADOPTION_GRANT_SCHEMA = "laplace.portable-runtime-adoption-grant/1"
RUNTIME_MESSAGE_BODY_CUSTODY_SCHEMA = "laplace.runtime-message-body-custody/1"
RUNTIME_MESSAGE_BODY_RESIDUAL_DECLARATION_SCHEMA = (
    "laplace.runtime-message-body-residual-declaration/1"
)
RUNTIME_CUSTODY_RESIDUAL_DECLARATION = (
    REPO_ROOT / "atlas" / "migrations" / "runtime-message-body-residuals-20260827.json"
)
_RUNTIME_CUSTODY_RESIDUAL_NAME = "historical-unavailable-message-bodies.json"
_HISTORICAL_UNAVAILABLE_REASON = "LEGACY_BODY_ABSENT_AT_CUSTODY_BOUNDARY"
_RUNTIME_CUSTODY_EVIDENCE_NAMES = (
    "events.legacy-imported.jsonl",
    "hive-migration-receipt.json",
    "hive-custody-receipt.json",
)
_HISTORICAL_UNAVAILABLE_ROW_KEYS = (
    "message_id",
    "cursor",
    "body_handle",
    "sent_event_id",
    "terminal_status",
    "terminal_event_id",
    "disposition",
    "last_pull_event_id",
    "reconstruction_handle",
    "sender_seat_id",
    "recipient_seat_id",
    "message_type",
    "assumption",
    "fibre",
    "reason",
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _runtime_receipt_payload_digest(receipt: Mapping[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receipt_payload_digest", None)
    return hash_bytes((canonical_json(payload) + "\n").encode("utf-8"))


def _canonical_blob_handles(root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Name immutable blobs while keeping transient/noncanonical paths explicit."""

    handles: list[str] = []
    residuals: list[str] = []
    if not root.exists():
        return (), ()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        name = path.name
        if (
            len(name) == 64
            and all(char in "0123456789abcdef" for char in name)
            and relative == f"{name[:2]}/{name}"
        ):
            handles.append("sha256:" + name)
        else:
            residuals.append(relative)
    return tuple(handles), tuple(residuals)


def _load_runtime_custody_residual_declaration(
    path: Path,
) -> tuple[dict[str, Any], bytes, str]:
    """Load the one tracked, author-ratified legacy residual declaration exactly."""

    try:
        raw = path.read_bytes()
        declaration = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise StoreError(
            "runtime message-body residual declaration is absent or malformed",
            path=str(path),
        ) from exc
    if not isinstance(declaration, dict) or set(declaration) != {
        "schema_version",
        "authorization",
        "historical_unavailable",
    }:
        raise StoreError("runtime message-body residual declaration has unknown fields")
    if declaration.get("schema_version") != RUNTIME_MESSAGE_BODY_RESIDUAL_DECLARATION_SCHEMA:
        raise StoreError(
            "runtime message-body residual declaration schema is unknown",
            got=declaration.get("schema_version"),
        )
    authorization = declaration.get("authorization")
    if not isinstance(authorization, dict) or set(authorization) != {
        "mode",
        "author",
        "ruling_date",
        "ruling_task_id",
        "ruling",
        "authorized_treatment",
    }:
        raise StoreError("runtime message-body residual authorization is malformed")
    if authorization.get("mode") != "exact-frozen-legacy-set":
        raise StoreError("runtime message-body residual authorization is not exact")
    if any(
        not isinstance(authorization.get(field), str) or not str(authorization[field]).strip()
        for field in (
            "author",
            "ruling_date",
            "ruling_task_id",
            "ruling",
            "authorized_treatment",
        )
    ):
        raise StoreError("runtime message-body residual ruling provenance is incomplete")
    rows = declaration.get("historical_unavailable")
    if not isinstance(rows, list) or not rows:
        raise StoreError("runtime message-body residual declaration is empty")
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(_HISTORICAL_UNAVAILABLE_ROW_KEYS):
            raise StoreError("runtime message-body residual row is malformed")
        if (
            isinstance(row.get("cursor"), bool)
            or not isinstance(row.get("cursor"), int)
            or int(row["cursor"]) < 1
        ):
            raise StoreError("runtime message-body residual cursor is malformed")
        if row.get("reason") != _HISTORICAL_UNAVAILABLE_REASON:
            raise StoreError("runtime message-body residual reason is unknown")
        if row.get("terminal_status") != "refused" or row.get("disposition") != "refused":
            raise StoreError("runtime message-body residual is not terminal REFUSED")
        for field in (
            "message_id",
            "body_handle",
            "sent_event_id",
            "terminal_event_id",
            "sender_seat_id",
            "recipient_seat_id",
            "message_type",
            "assumption",
            "fibre",
        ):
            if not isinstance(row.get(field), str) or not str(row[field]).strip():
                raise StoreError(
                    "runtime message-body residual identity is incomplete", field=field
                )
        if (
            row.get("last_pull_event_id") is not None
            or row.get("reconstruction_handle") is not None
        ):
            raise StoreError("runtime message-body residual claims delivered content")
    ordered = sorted(rows, key=lambda row: (int(row["cursor"]), str(row["message_id"])))
    if rows != ordered:
        raise StoreError("runtime message-body residual rows are not canonically ordered")
    message_ids = [str(row["message_id"]) for row in rows]
    if len(message_ids) != len(set(message_ids)):
        raise StoreError("runtime message-body residual repeats a message")
    return declaration, raw, _file_sha256(path)


def _runtime_message_body_relation(
    state: ConceptricState,
    available_handles: set[str],
) -> list[dict[str, Any]]:
    return [
        {
            "message_id": message_id,
            "cursor": record.message.cursor,
            "body_handle": record.message.body_handle,
            "state": (
                "available"
                if record.message.body_handle in available_handles
                else "historical-unavailable"
            ),
        }
        for message_id, record in sorted(
            state.messages.items(),
            key=lambda item: (item[1].message.cursor, item[0]),
        )
    ]


def _historical_unavailable_row(*, state: ConceptricState, message_id: str) -> dict[str, Any]:
    record = state.messages[message_id]
    terminal_event_id = record.acknowledgement_event_id
    acknowledgement = (
        None
        if terminal_event_id is None
        else state.graph_objects.get(f"acknowledgement:{terminal_event_id}")
    )
    disposition = None if acknowledgement is None else acknowledgement.attributes.get("disposition")
    return {
        "message_id": message_id,
        "cursor": record.message.cursor,
        "body_handle": record.message.body_handle,
        "sent_event_id": record.sent_event_id,
        "terminal_status": record.status.value,
        "terminal_event_id": terminal_event_id,
        "disposition": disposition,
        "last_pull_event_id": record.last_pull_event_id,
        "reconstruction_handle": record.reconstruction_handle,
        "sender_seat_id": record.message.sender_seat_id,
        "recipient_seat_id": record.message.recipient_seat_id,
        "message_type": record.message.message_type,
        "assumption": record.assumption,
        "fibre": record.fibre,
        "reason": _HISTORICAL_UNAVAILABLE_REASON,
    }


def _runtime_message_body_custody(
    *,
    state: ConceptricState,
    available_handles: set[str],
    declaration: Mapping[str, Any],
    declaration_sha256: str,
) -> dict[str, Any]:
    """Prove the actual missing relation equals the exact frozen legacy set."""

    relation = _runtime_message_body_relation(state, available_handles)
    missing_ids = [row["message_id"] for row in relation if row["state"] != "available"]
    actual_rows = [
        _historical_unavailable_row(state=state, message_id=str(message_id))
        for message_id in missing_ids
    ]
    declared_rows = declaration.get("historical_unavailable")
    if actual_rows != declared_rows:
        raise StoreError(
            "runtime Atlas missing message bodies do not equal the authorized legacy set",
            actual_message_ids=[row["message_id"] for row in actual_rows],
            declared_message_ids=(
                []
                if not isinstance(declared_rows, list)
                else [row.get("message_id") for row in declared_rows if isinstance(row, Mapping)]
            ),
        )
    declared_handles = {str(row["body_handle"]) for row in actual_rows}
    if declared_handles.intersection(available_handles):
        raise StoreError("runtime Atlas residual declaration names a present body")
    required_handles = {record.message.body_handle for record in state.messages.values()}
    historical_root = chash(
        {
            "schema_version": "laplace.runtime-message-body-historical-unavailable-set/1",
            "rows": actual_rows,
        }
    )
    relation_root = chash(
        {
            "schema_version": "laplace.runtime-message-body-relation/1",
            "rows": relation,
        }
    )
    authorization = declaration["authorization"]
    return {
        "schema_version": RUNTIME_MESSAGE_BODY_CUSTODY_SCHEMA,
        "referenced_message_count": len(state.messages),
        "unique_body_handle_count": len(required_handles),
        "available_body_handle_count": len(required_handles & available_handles),
        "historical_unavailable_message_count": len(actual_rows),
        "historical_unavailable_body_handle_count": len(declared_handles),
        "historical_unavailable": actual_rows,
        "historical_unavailable_root": historical_root,
        "complete_relation_root": relation_root,
        "authorization": {
            "mode": "exact-frozen-legacy-set",
            "declaration_path": _RUNTIME_CUSTODY_RESIDUAL_NAME,
            "tracked_declaration_ref": (
                "atlas/migrations/runtime-message-body-residuals-20260827.json"
            ),
            "declaration_sha256": declaration_sha256,
            "declaration_root": chash(dict(declaration)),
            "author": authorization["author"],
            "ruling_date": authorization["ruling_date"],
            "ruling_task_id": authorization["ruling_task_id"],
            "authorized_treatment": authorization["authorized_treatment"],
        },
    }


def _runtime_custody_evidence_manifest(root: Path) -> dict[str, Any]:
    """Bind every co-resident receipt that can affect later writable admission."""

    files = []
    for name in _RUNTIME_CUSTODY_EVIDENCE_NAMES:
        path = root / name
        if not path.exists():
            continue
        if not path.is_file():
            raise StoreError(
                "runtime Atlas co-resident custody evidence is not a file",
                path=str(path),
            )
        files.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": _file_sha256(path),
            }
        )
    manifest_root = chash(
        {
            "schema_version": "laplace.runtime-atlas-co-resident-evidence-files/1",
            "files": files,
        }
    )
    return {
        "schema_version": "laplace.runtime-atlas-co-resident-evidence/1",
        "files": files,
        "manifest_root": manifest_root,
    }


def _runtime_capsule_layout(root: Path) -> dict[str, Any]:
    """Verify the v2 capsule is one allowlisted, non-aliased filesystem object."""

    allowed_files = {
        "conceptric.sqlite3",
        "RECEIPT.json",
        _RUNTIME_CUSTODY_RESIDUAL_NAME,
        *_RUNTIME_CUSTODY_EVIDENCE_NAMES,
    }
    allowed_directories = {"blobs", "hives"}
    if root.is_symlink() or not root.is_dir():
        raise StoreError("runtime custody capsule root is not a real directory")
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise StoreError("runtime custody capsule contains a symlink", path=relative)
        if path.name.endswith(("-wal", "-shm")):
            raise StoreError("runtime custody capsule contains a SQLite sidecar", path=relative)
        if path.parent == root:
            if stat.S_ISREG(mode) and path.name not in allowed_files:
                raise StoreError("runtime custody capsule contains an extra file", path=relative)
            if stat.S_ISDIR(mode) and path.name not in allowed_directories:
                raise StoreError("runtime custody capsule contains an extra directory", path=relative)
        if stat.S_ISREG(mode):
            if path.stat().st_nlink != 1:
                raise StoreError("runtime custody capsule contains a hard-linked file", path=relative)
            files.append(
                {
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
            )
        elif not stat.S_ISDIR(mode):
            raise StoreError("runtime custody capsule contains an unknown filesystem object", path=relative)
    if not (root / "conceptric.sqlite3").is_file() or not (root / "RECEIPT.json").is_file():
        raise StoreError("runtime custody capsule is missing its ledger or receipt")
    return {
        "schema_version": "laplace.runtime-custody-filesystem-manifest/1",
        "files": files,
        "manifest_root": chash(
            {
                "schema_version": "laplace.runtime-custody-filesystem-manifest/1",
                "files": files,
            }
        ),
    }


def _sqlite_backup(source: Path, destination: Path) -> str:
    """Take one online-safe SQLite snapshot, including committed WAL frames."""

    source_db: sqlite3.Connection | None = None
    destination_db: sqlite3.Connection | None = None
    try:
        source_db = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        destination_db = sqlite3.connect(destination)
        source_db.backup(destination_db)
        # The backup contains every committed source WAL frame in its main database.
        # Keeping the source's WAL journal mode would make the point-in-time object mint
        # mutable ``-wal``/``-shm`` coordination files on its first verification. Normalize
        # the finished copy before hashing and atomic publication; this changes no row.
        mode = destination_db.execute("PRAGMA journal_mode = DELETE").fetchone()
        if mode is None or str(mode[0]).lower() != "delete":
            raise StoreError(
                "runtime Atlas SQLite backup could not become self-contained",
                destination=str(destination),
                journal_mode=None if mode is None else str(mode[0]),
            )
        integrity = destination_db.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error as exc:
        raise StoreError(
            "runtime Atlas SQLite backup failed",
            source=str(source),
            destination=str(destination),
            error=str(exc),
        ) from exc
    finally:
        if destination_db is not None:
            destination_db.close()
        if source_db is not None:
            source_db.close()
    verdict = None if integrity is None else str(integrity[0])
    if verdict != "ok":
        raise StoreError(
            "runtime Atlas SQLite backup failed integrity verification",
            destination=str(destination),
            integrity_check=verdict,
        )
    return verdict


def _copy_runtime_event_hives(*, source: ConceptricStore, snapshot_root: Path) -> tuple[str, ...]:
    """Copy only event chunks named by the backed-up compact ledger."""

    handles = _event_hive_handles(snapshot_root / "conceptric.sqlite3")
    if not handles:
        return ()
    relative_hive_root = source.hive_root.relative_to(source.root)
    destination = CompressedHive(snapshot_root / relative_hive_root)
    copied = []
    for handle in handles:
        if destination.put(source.hive.get(handle)) != handle:
            raise StoreError("runtime Atlas event hive changed while copying", handle=handle)
        copied.append(handle)
    return tuple(copied)


def _event_hive_handles(ledger: Path) -> tuple[str, ...]:
    """Return the compact ledger's exact event-hive frontier, or empty for schema v1."""

    with sqlite3.connect(
        ledger.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
    ) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(events)")}
        return (
            tuple(
                str(row[0])
                for row in connection.execute("SELECT event_handle FROM events ORDER BY sequence")
            )
            if "event_handle" in columns
            else ()
        )


def _runtime_source_git_coordinate() -> dict[str, str]:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD", "HEAD^{tree}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    commit, tree = completed.stdout.splitlines()
    return {
        "schema_version": "laplace.runtime-custody-source-git/1",
        "commit": commit,
        "tree": tree,
    }


def _runtime_source_recovery_coordinate() -> dict[str, str]:
    from laplace.representation.recovery_coordinate import DEFAULT_COORDINATE, canonical_payload_digest

    document = json.loads(DEFAULT_COORDINATE.read_text(encoding="utf-8"))
    actual = canonical_payload_digest(document)
    if actual != document.get("coordinate_payload_digest"):
        raise StoreError("runtime custody source recovery coordinate payload does not verify")
    return {
        "path": DEFAULT_COORDINATE.relative_to(REPO_ROOT).as_posix(),
        "payload_digest": actual,
    }


def verify_runtime_custody(snapshot_root: str | os.PathLike[str]) -> dict[str, Any]:
    """Reconstruct and re-hash one exported runtime Atlas snapshot without writing it."""

    root = Path(snapshot_root).resolve()
    receipt_path = root / "RECEIPT.json"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StoreError(
            "runtime Atlas custody receipt is absent or malformed",
            path=str(receipt_path),
        ) from exc
    receipt_schema = receipt.get("schema_version")
    if receipt_schema not in {LEGACY_RUNTIME_CUSTODY_SCHEMA, RUNTIME_CUSTODY_SCHEMA}:
        raise StoreError(
            "runtime Atlas custody receipt schema is unknown",
            got=receipt_schema,
        )
    if receipt_schema == RUNTIME_CUSTODY_SCHEMA:
        _runtime_capsule_layout(root)
        if receipt.get("authenticated") is not False or receipt.get(
            "integrity_boundary"
        ) != "CHECKSUMMED-CRUTCH":
            raise StoreError("runtime Atlas custody v2 overstates its integrity boundary")
        if _runtime_receipt_payload_digest(receipt) != receipt.get(
            "receipt_payload_digest"
        ):
            raise StoreError("runtime Atlas custody receipt payload digest does not verify")
    ledger = root / "conceptric.sqlite3"
    if _file_sha256(ledger) != receipt.get("ledger", {}).get("sha256"):
        raise StoreError("runtime Atlas custody ledger hash disagrees with its receipt")
    with sqlite3.connect(
        ledger.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
    ) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
    if integrity is None or str(integrity[0]) != "ok":
        raise StoreError("runtime Atlas custody ledger fails integrity_check")
    co_resident_evidence = receipt.get("co_resident_evidence")
    if co_resident_evidence is not None:
        if not isinstance(co_resident_evidence, Mapping):
            raise StoreError("runtime Atlas co-resident evidence manifest is malformed")
        expected_evidence = _runtime_custody_evidence_manifest(root)
        if dict(co_resident_evidence) != expected_evidence:
            raise StoreError(
                "runtime Atlas co-resident custody evidence disagrees with its receipt"
            )

    # A published custody directory is an immutable point-in-time object. Ordinary
    # ``mode=ro`` still creates SQLite WAL coordination sidecars beside a WAL-mode
    # database, making a claimed read-only verification dirty the Git snapshot it checks.
    store = ConceptricStore(
        root, read_only=True, immutable=True,
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    state = store.replay_authority_only()
    if state.event_count != int(
        receipt.get("event_count", -1)
    ) or state.head_event_id != receipt.get("head_event_id"):
        raise StoreError(
            "runtime Atlas custody replay disagrees with its receipt",
            expected_event_count=receipt.get("event_count"),
            actual_event_count=state.event_count,
            expected_head_event_id=receipt.get("head_event_id"),
            actual_head_event_id=state.head_event_id,
        )
    drift = ConceptricStore.read_drift_token(root, immutable=True)
    if drift["head_record_digest"] != receipt.get("head_record_digest"):
        raise StoreError("runtime Atlas custody causal head disagrees with its receipt")
    source_capture = receipt.get("source_capture")
    if source_capture is not None:
        if not isinstance(source_capture, Mapping):
            raise StoreError("runtime Atlas source-capture receipt is malformed")
        before = source_capture.get("before")
        after = source_capture.get("after")
        expected_drift = {
            "schema_version": "atlas.conceptric-drift-token/1",
            "cursor": state.event_count,
            "head_event_id": state.head_event_id,
            "head_record_digest": drift["head_record_digest"],
        }
        if before != after or before != expected_drift:
            raise StoreError("runtime Atlas source capture is not one stable generation")

    blobs = BlobStore(root / "blobs")
    handles, residuals = _canonical_blob_handles(root / "blobs")
    if residuals:
        raise StoreError(
            "runtime Atlas custody contains noncanonical blob paths",
            paths=residuals[:12],
            omitted=max(0, len(residuals) - 12),
        )
    for handle in handles:
        blobs.get(handle)
    blob_root = chash({"handles": list(handles)})
    if len(handles) != int(receipt.get("blobs", {}).get("count", -1)) or blob_root != receipt.get(
        "blobs", {}
    ).get("manifest_root"):
        raise StoreError("runtime Atlas custody blob manifest disagrees with its receipt")
    if source_capture is not None and (
        source_capture.get("blob_manifest_before") != blob_root
        or source_capture.get("blob_manifest_after") != blob_root
    ):
        raise StoreError("runtime Atlas source blob generation was not stable")
    required = {record.message.body_handle for record in state.messages.values()}
    missing = tuple(sorted(required - set(handles)))
    message_body_custody = receipt.get("message_body_custody")
    message_body_custody_root = None
    declaration_path = root / _RUNTIME_CUSTODY_RESIDUAL_NAME
    if missing:
        if not isinstance(message_body_custody, Mapping):
            raise StoreError(
                "runtime Atlas custody is missing message bodies",
                missing=missing[:12],
                omitted=max(0, len(missing) - 12),
            )
        declaration, _raw, declaration_sha256 = _load_runtime_custody_residual_declaration(
            declaration_path
        )
        tracked_declaration, _tracked_raw, tracked_declaration_sha256 = (
            _load_runtime_custody_residual_declaration(RUNTIME_CUSTODY_RESIDUAL_DECLARATION)
        )
        if declaration != tracked_declaration or declaration_sha256 != tracked_declaration_sha256:
            raise StoreError(
                "runtime Atlas residual declaration is not the tracked author-ratified set"
            )
        expected_body_custody = _runtime_message_body_custody(
            state=state,
            available_handles=set(handles),
            declaration=declaration,
            declaration_sha256=declaration_sha256,
        )
        if dict(message_body_custody) != expected_body_custody:
            raise StoreError("runtime Atlas message-body residual subreceipt does not verify")
        message_body_custody_root = chash(expected_body_custody)
    elif message_body_custody is not None or declaration_path.exists():
        raise StoreError(
            "runtime Atlas custody claims historical-unavailable bodies that are present"
        )
    if len(required) != int(receipt.get("blobs", {}).get("required_message_body_count", -1)):
        raise StoreError("runtime Atlas custody message-body count disagrees with its receipt")
    event_hives = _event_hive_handles(ledger)
    event_hive_root = chash({"handles": list(event_hives)})
    if len(event_hives) != int(
        receipt.get("event_hives", {}).get("count", -1)
    ) or event_hive_root != receipt.get("event_hives", {}).get("manifest_root"):
        raise StoreError("runtime Atlas custody event-hive frontier disagrees with its receipt")
    identity = {
        "source_schema": store.schema_version,
        "event_count": state.event_count,
        "head_event_id": state.head_event_id,
        "head_record_digest": drift["head_record_digest"],
        "ledger_sha256": receipt["ledger"]["sha256"],
        "blob_manifest_root": blob_root,
        "event_hive_manifest_root": event_hive_root,
    }
    if message_body_custody_root is not None:
        identity["message_body_custody_root"] = message_body_custody_root
    if source_capture is not None:
        identity["source_capture_root"] = chash(dict(source_capture))
    if co_resident_evidence is not None:
        identity["co_resident_evidence_root"] = chash(dict(co_resident_evidence))
    if receipt_schema == RUNTIME_CUSTODY_SCHEMA:
        source_checkpoint = receipt.get("source_checkpoint")
        source_context = receipt.get("source_authority_context")
        source_git = receipt.get("source_git")
        custody_roots = receipt.get("custody_roots")
        if not all(
            isinstance(value, Mapping)
            for value in (source_checkpoint, source_context, source_git, custody_roots)
        ):
            raise StoreError("runtime Atlas custody v2 provenance is incomplete")
        context_body = {
            key: value for key, value in source_context.items() if key != "evidence_root"
        }
        if (
            source_context.get("schema_version") != "atlas.authority-context-evidence/1"
            or chash(context_body) != source_context.get("evidence_root")
        ):
            raise StoreError("runtime Atlas source authority context does not verify")
        if (
            source_checkpoint.get("cursor") != state.event_count
            or source_checkpoint.get("head_event_id") != state.head_event_id
            or source_checkpoint.get("head_record_digest") != drift["head_record_digest"]
            or not str(source_checkpoint.get("checkpoint_digest") or "").startswith("sha256:")
        ):
            raise StoreError("runtime Atlas source checkpoint disagrees with its ledger")
        for field in ("commit", "tree"):
            value = str(source_git.get(field) or "")
            if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
                raise StoreError("runtime Atlas source Git identity is malformed", field=field)
        recovery_digest = str(receipt.get("recovery_coordinate_payload_digest") or "")
        if not recovery_digest.startswith("sha256:"):
            raise StoreError("runtime Atlas recovery-coordinate provenance is malformed")
        expected_roots = {
            "ledger": receipt["ledger"]["sha256"],
            "blobs": blob_root,
            "event_hives": event_hive_root,
            "evidence": (
                None
                if co_resident_evidence is None
                else co_resident_evidence.get("manifest_root")
            ),
            "source_authority_context": source_context.get("evidence_root"),
        }
        if dict(custody_roots) != expected_roots:
            raise StoreError("runtime Atlas custody v2 roots disagree with verified bytes")
        identity.update(
            {
                "receipt_schema": RUNTIME_CUSTODY_SCHEMA,
                "source_checkpoint_root": chash(dict(source_checkpoint)),
                "source_authority_context_root": source_context["evidence_root"],
                "source_git_root": chash(dict(source_git)),
                "recovery_coordinate_payload_digest": recovery_digest,
            }
        )
    if receipt.get("source_schema") != store.schema_version:
        raise StoreError("runtime Atlas custody schema disagrees with its receipt")
    if chash(identity) != receipt.get("snapshot_id"):
        raise StoreError("runtime Atlas custody snapshot identity does not verify")
    return {
        "schema_version": receipt_schema,
        "receipt_schema": receipt_schema,
        "status": "verified",
        "snapshot_id": receipt["snapshot_id"],
        "event_count": state.event_count,
        "head_event_id": state.head_event_id,
        "head_record_digest": drift["head_record_digest"],
        "blob_count": len(handles),
        "required_message_blob_count": len(required),
        "historical_unavailable_message_count": (
            0
            if message_body_custody is None
            else int(message_body_custody["historical_unavailable_message_count"])
        ),
        "complete_message_body_relation_root": (
            None if message_body_custody is None else message_body_custody["complete_relation_root"]
        ),
        "storage_separation": receipt["storage_separation"],
        "off_machine_state": "unknown; never inferred from a filesystem device id",
        "read_only": True,
        "authenticated": False,
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
        "receipt_payload_digest": receipt.get("receipt_payload_digest"),
    }


def export_runtime_custody(
    *,
    destination: str | os.PathLike[str],
    admit_declared_historical_unavailable: bool = False,
) -> dict[str, Any]:
    """Publish one verified destination-explicit runtime snapshot without touching authority.

    This door is never scheduled or called implicitly. Gerard chooses the destination; the
    implementation snapshots SQLite online, copies content-addressed bodies and event hives,
    reconstructs the result, and only then atomically publishes it. A different filesystem is
    reported as such, never inflated into an off-machine claim. Missing message bodies remain a
    refusal unless the caller explicitly admits the one tracked, exact historical declaration.
    """

    source_root = store_root().resolve()
    source_context_evidence = ConceptricStore.authority_context_evidence(
        source_root, store_role="live-runtime-fabric",
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    source_context = dict(source_context_evidence["roots"])
    source_epoch = ConceptricStore.read_authority_checkpoint(
        source_root, expected_context=source_context,
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    if source_epoch.get("status") != "CURRENT":
        raise HistoryChainMismatch("runtime custody source authority checkpoint is not CURRENT")
    source_checkpoint_body = dict(source_epoch["effective_checkpoint"])
    source_checkpoint = {
        "schema_version": "laplace.runtime-custody-source-checkpoint/1",
        "checkpoint_digest": source_epoch["effective_checkpoint_digest"],
        "cursor": source_checkpoint_body["cursor"],
        "head_event_id": source_checkpoint_body["head_event_id"],
        "head_record_digest": source_checkpoint_body["head_record_digest"],
    }
    source_git = _runtime_source_git_coordinate()
    source_coordinate = _runtime_source_recovery_coordinate()
    target = Path(destination).expanduser().resolve()
    if target == source_root or source_root in target.parents:
        raise StoreError(
            "runtime Atlas custody destination cannot sit inside live authority",
            source=str(source_root),
            destination=str(target),
        )
    if target.exists():
        raise StoreError(
            "runtime Atlas custody destination already exists; snapshots never overwrite",
            destination=str(target),
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        source_store = _read_store()
        source_blobs = BlobStore(source_root / "blobs")
        destination_blobs = BlobStore(pending / "blobs")
        # The SQLite backup, event hives, co-resident custody evidence and provider blobs are one
        # capture generation. Atlas writers use this lock exclusively. Provider blob creation can
        # precede an append, so its complete canonical manifest is also compared before/after.
        with source_store._locked(shared=True):
            source_drift_before = ConceptricStore.read_drift_token(source_root)
            blob_handles, blob_residuals = _canonical_blob_handles(source_root / "blobs")
            source_wal = source_root / "conceptric.sqlite3-wal"
            wal_bytes = source_wal.stat().st_size if source_wal.is_file() else 0
            integrity = _sqlite_backup(source_store.path, pending / "conceptric.sqlite3")
            event_hives = _copy_runtime_event_hives(
                source=source_store,
                snapshot_root=pending,
            )
            for evidence_path in (
                source_store.legacy_receipt_path,
                source_store.migration_receipt_path,
                source_store.custody_receipt_path,
            ):
                if evidence_path.is_file():
                    write_atomic(pending / evidence_path.name, evidence_path.read_bytes())
            for handle in blob_handles:
                if destination_blobs.put(source_blobs.get(handle)) != handle:
                    raise StoreError("runtime Atlas blob changed while copying", handle=handle)
            source_drift_after = ConceptricStore.read_drift_token(source_root)
            blob_handles_after, blob_residuals_after = _canonical_blob_handles(
                source_root / "blobs"
            )
            if (
                source_drift_after != source_drift_before
                or blob_handles_after != blob_handles
                or blob_residuals_after != blob_residuals
            ):
                raise StoreError(
                    "runtime Atlas source generation moved during custody capture",
                    before=source_drift_before,
                    after=source_drift_after,
                )

        snapshot_store = ConceptricStore(
            pending, read_only=True, immutable=True,
            extra_authority_files=EXTRA_AUTHORITY_FILES,
        )
        state = snapshot_store.replay_authority_only()
        drift = ConceptricStore.read_drift_token(pending, immutable=True)
        required = {record.message.body_handle for record in state.messages.values()}
        missing = tuple(sorted(required - set(blob_handles)))
        message_body_custody = None
        if missing:
            if not admit_declared_historical_unavailable:
                raise StoreError(
                    "runtime Atlas snapshot is missing message bodies",
                    missing=missing[:12],
                    omitted=max(0, len(missing) - 12),
                )
            declaration, declaration_raw, declaration_sha256 = (
                _load_runtime_custody_residual_declaration(RUNTIME_CUSTODY_RESIDUAL_DECLARATION)
            )
            message_body_custody = _runtime_message_body_custody(
                state=state,
                available_handles=set(blob_handles),
                declaration=declaration,
                declaration_sha256=declaration_sha256,
            )
            write_atomic(pending / _RUNTIME_CUSTODY_RESIDUAL_NAME, declaration_raw)
        ledger_hash = _file_sha256(pending / "conceptric.sqlite3")
        blob_manifest_root = chash({"handles": list(blob_handles)})
        event_hive_root = chash({"handles": list(event_hives)})
        co_resident_evidence = _runtime_custody_evidence_manifest(pending)
        source_device = source_root.stat().st_dev
        destination_device = target.parent.stat().st_dev
        storage_separation = (
            "different-filesystem"
            if source_device != destination_device
            else "same-filesystem-mitigation-only"
        )
        source_capture = {
            "schema_version": "laplace.runtime-atlas-source-capture/1",
            "coordination": "shared-conceptric-lock-plus-stable-blob-manifest",
            "before": source_drift_before,
            "after": source_drift_after,
            "blob_manifest_before": blob_manifest_root,
            "blob_manifest_after": chash({"handles": list(blob_handles_after)}),
        }
        identity = {
            "source_schema": source_store.schema_version,
            "event_count": state.event_count,
            "head_event_id": state.head_event_id,
            "head_record_digest": drift["head_record_digest"],
            "ledger_sha256": ledger_hash,
            "blob_manifest_root": blob_manifest_root,
            "event_hive_manifest_root": event_hive_root,
            "source_capture_root": chash(source_capture),
            "co_resident_evidence_root": chash(co_resident_evidence),
            "receipt_schema": RUNTIME_CUSTODY_SCHEMA,
            "source_checkpoint_root": chash(source_checkpoint),
            "source_authority_context_root": source_context_evidence["evidence_root"],
            "source_git_root": chash(source_git),
            "recovery_coordinate_payload_digest": source_coordinate["payload_digest"],
        }
        if message_body_custody is not None:
            identity["message_body_custody_root"] = chash(message_body_custody)
        receipt = {
            "schema_version": RUNTIME_CUSTODY_SCHEMA,
            "authenticated": False,
            "integrity_boundary": "CHECKSUMMED-CRUTCH",
            "snapshot_id": chash(identity),
            "taken_at": _now(),
            "source": str(source_root),
            "source_schema": source_store.schema_version,
            "event_count": state.event_count,
            "head_event_id": state.head_event_id,
            "head_record_digest": drift["head_record_digest"],
            "ledger": {
                "path": "conceptric.sqlite3",
                "bytes": (pending / "conceptric.sqlite3").stat().st_size,
                "sha256": ledger_hash,
                "integrity_check": integrity,
                "source_wal_bytes_observed": wal_bytes,
                "online_backup_includes_committed_wal": True,
            },
            "blobs": {
                "count": len(blob_handles),
                "manifest_root": blob_manifest_root,
                "required_message_body_count": len(required),
                "source_noncanonical_residuals": list(blob_residuals),
            },
            "event_hives": {
                "count": len(event_hives),
                "manifest_root": event_hive_root,
            },
            "co_resident_evidence": co_resident_evidence,
            "custody_roots": {
                "ledger": ledger_hash,
                "blobs": blob_manifest_root,
                "event_hives": event_hive_root,
                "evidence": co_resident_evidence["manifest_root"],
                "source_authority_context": source_context_evidence["evidence_root"],
            },
            "source_checkpoint": source_checkpoint,
            "source_authority_context": source_context_evidence,
            "source_git": source_git,
            "recovery_coordinate_payload_digest": source_coordinate["payload_digest"],
            "recovery_coordinate_source_path": source_coordinate["path"],
            "source_capture": source_capture,
            "storage_separation": storage_separation,
            "off_machine_state": "unknown; never inferred from a filesystem device id",
            "atomic_publish": True,
            "receipt_payload_digest": "",
        }
        if message_body_custody is not None:
            receipt["message_body_custody"] = message_body_custody
        receipt["receipt_payload_digest"] = _runtime_receipt_payload_digest(receipt)
        write_atomic(
            pending / "RECEIPT.json",
            (canonical_json(receipt) + "\n").encode("utf-8"),
        )
        verified = verify_runtime_custody(pending)
        os.replace(pending, target)
        return {
            **verified,
            "destination": str(target),
            "published": True,
        }
    except Exception:
        shutil.rmtree(pending, ignore_errors=True)
        raise


def _runtime_writable_adoption_source(root: Path) -> tuple[dict[str, Any], str]:
    """Read the immutable travelling receipt retained as the adoption predecessor."""

    receipt_path = root / "RECEIPT.json"
    try:
        raw = receipt_path.read_bytes()
        receipt = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise StoreError(
            "portable runtime custody source receipt is absent or malformed",
            path=str(receipt_path),
        ) from exc
    if receipt.get("schema_version") != RUNTIME_CUSTODY_SCHEMA:
        raise StoreError("portable runtime custody adoption requires a capsule v2 receipt")
    if _runtime_receipt_payload_digest(receipt) != receipt.get("receipt_payload_digest"):
        raise StoreError("portable runtime custody source receipt digest does not verify")
    return receipt, hash_bytes(raw)


def _committed_runtime_recovery_grant(
    *,
    coordinate_path: str | os.PathLike[str],
    source_root: Path,
    source_receipt: Mapping[str, Any],
    source_receipt_sha256: str,
    destination_root: Path,
    destination_context_evidence: Mapping[str, Any],
    expected_grant_root: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Bind a capsule to an independently committed coordinate and destination."""

    from laplace.representation.recovery_coordinate import canonical_payload_digest, verify_runtime_recovery_point

    path = Path(coordinate_path).expanduser().resolve()
    try:
        relative = path.relative_to(REPO_ROOT).as_posix()
    except ValueError as exc:
        raise StoreError("portable adoption coordinate is outside repository custody") from exc
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise StoreError(
            "portable adoption coordinate is absent or unreadable",
            path=str(path),
        ) from exc
    completed = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0 or completed.stdout != raw:
        raise StoreError("portable adoption coordinate is not exact committed custody")
    try:
        coordinate = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise StoreError("portable adoption coordinate is malformed") from exc
    coordinate_digest = canonical_payload_digest(coordinate)
    if coordinate_digest != coordinate.get("coordinate_payload_digest"):
        raise StoreError("portable adoption coordinate payload digest does not verify")
    point = coordinate.get("runtime_recovery_point")
    coordinate_grant = coordinate.get("runtime_recovery_grant")
    if not isinstance(point, Mapping) or not isinstance(coordinate_grant, Mapping):
        raise StoreError("portable adoption coordinate omits its external recovery grant")
    verify_runtime_recovery_point(point, source_root)
    grant_anchor_body = dict(coordinate_grant)
    grant_anchor_root = grant_anchor_body.pop("grant_anchor_root", None)
    if chash(grant_anchor_body) != grant_anchor_root:
        raise StoreError("portable adoption coordinate grant anchor does not verify")
    if (
        coordinate_grant.get("point_root") != point.get("point_root")
        or coordinate_grant.get("source_snapshot_id") != source_receipt.get("snapshot_id")
        or coordinate_grant.get("source_checkpoint_digest")
        != (source_receipt.get("source_checkpoint") or {}).get("checkpoint_digest")
    ):
        raise HistoryChainMismatch("portable adoption coordinate names another source point")
    grant_identity = {
        "schema_version": RUNTIME_ADOPTION_GRANT_SCHEMA,
        "source_snapshot_id": source_receipt["snapshot_id"],
        "source_receipt_sha256": source_receipt_sha256,
        "source_checkpoint_digest": source_receipt["source_checkpoint"][
            "checkpoint_digest"
        ],
        "recovery_coordinate_payload_digest": coordinate_digest,
        "recovery_grant_anchor_root": grant_anchor_root,
        "destination_root": os.fspath(destination_root),
        "destination_context_evidence_root": destination_context_evidence["evidence_root"],
        "target_store_role": "live-runtime-fabric",
        "target_store_schema": CONCEPTRIC_DB_SCHEMA,
        "predecessor_adoption_root": point["predecessor_adoption_root"],
    }
    grant_root = chash(grant_identity)
    if expected_grant_root is not None and grant_root != expected_grant_root:
        raise HistoryChainMismatch(
            "portable adoption external grant root moved",
            expected=expected_grant_root,
            actual=grant_root,
        )
    return grant_identity, coordinate_digest, dict(point)


def verify_writable_runtime_custody(
    snapshot_root: str | os.PathLike[str],
    *,
    expected_snapshot_id: str | None = None,
    expected_grant_root: str | None = None,
    canonical_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Verify one adopted blank-machine store without treating its source receipt as current.

    ``RECEIPT.json`` remains immutable evidence of the travelling predecessor.  The current
    checkpoint and custody seal are verified independently and must name the same event/head and
    exact provider blobs/hives.  No replay result is promoted beyond CHECKSUMMED-CRUTCH.
    """

    root = Path(snapshot_root).expanduser().resolve()
    source_receipt, source_receipt_sha256 = _runtime_writable_adoption_source(root)
    adoption = ConceptricStore.read_portable_authority_adoption(
        root, expected_store_role="live-runtime-fabric",
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    if adoption is None:
        raise StoreError("runtime custody has no portable writable adoption")
    snapshot_id = str(source_receipt.get("snapshot_id") or "")
    if expected_snapshot_id is not None and snapshot_id != expected_snapshot_id:
        raise HistoryChainMismatch(
            "portable runtime custody snapshot id moved",
            expected=expected_snapshot_id,
            actual=snapshot_id,
        )
    source_ledger_sha256 = source_receipt.get("ledger", {}).get("sha256")
    source_expected = {
        "source_snapshot_id": snapshot_id,
        "source_receipt_sha256": source_receipt_sha256,
        "source_ledger_sha256": source_ledger_sha256,
        "source_cursor": source_receipt.get("event_count"),
        "source_head_event_id": source_receipt.get("head_event_id"),
        "source_head_record_digest": source_receipt.get("head_record_digest"),
        "source_blob_manifest_root": (source_receipt.get("blobs") or {}).get(
            "manifest_root"
        ),
        "source_event_hive_manifest_root": (
            source_receipt.get("event_hives") or {}
        ).get("manifest_root"),
        "source_evidence_manifest_root": (
            source_receipt.get("co_resident_evidence") or {}
        ).get("manifest_root"),
        "source_authority_context_evidence": source_receipt.get(
            "source_authority_context"
        ),
        "source_git_commit": (source_receipt.get("source_git") or {}).get("commit"),
        "source_git_tree": (source_receipt.get("source_git") or {}).get("tree"),
    }
    mismatches = {
        key: {"expected": value, "adoption": adoption.get(key)}
        for key, value in source_expected.items()
        if value != adoption.get(key)
    }
    if mismatches:
        raise HistoryChainMismatch(
            "portable writable adoption contradicts its source receipt",
            mismatches=mismatches,
        )

    destination = (
        root if canonical_root is None else Path(canonical_root).expanduser().resolve()
    )
    context_evidence = ConceptricStore.authority_context_evidence(
        destination, store_role="live-runtime-fabric",
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    context = dict(context_evidence["roots"])
    if context != adoption["target_context"]:
        raise HistoryChainMismatch(
            "portable writable adoption context moved",
            expected=adoption["target_context"],
            actual=context,
        )
    if context_evidence != adoption["target_context_evidence"]:
        raise HistoryChainMismatch("portable writable adoption destination evidence moved")
    if expected_grant_root is not None and adoption["grant_root"] != expected_grant_root:
        raise HistoryChainMismatch(
            "portable writable adoption grant moved",
            expected=expected_grant_root,
            actual=adoption["grant_root"],
        )
    drift = ConceptricStore.read_drift_token(root)
    expected_drift = {
        "schema_version": "atlas.conceptric-drift-token/1",
        "cursor": adoption["source_cursor"],
        "head_event_id": adoption["source_head_event_id"],
        "head_record_digest": adoption["source_head_record_digest"],
    }
    if drift != expected_drift:
        raise HistoryChainMismatch(
            "portable writable adoption event history moved",
            expected=expected_drift,
            actual=drift,
        )
    fast = ConceptricStore.read_authority_checkpoint(root, expected_context=context,
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    if (
        fast.get("status") != "CURRENT"
        or fast.get("integrity_boundary", {}).get("status") != "CHECKSUMMED-CRUTCH"
        or fast.get("effective_checkpoint_digest")
        != adoption["target_checkpoint_digest"]
    ):
        raise HistoryChainMismatch(
            "portable writable adoption fast checkpoint is not current",
            fast=fast,
        )
    deep = ConceptricStore.verify_authority_checkpoint_deep(
        root,
        expected_context=context,
        expected_store_role="live-runtime-fabric",
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    if (
        deep.get("status") != "EXACT"
        or not deep.get("fast_deep_equal")
        or deep.get("candidate_checkpoint_digest")
        != adoption["target_checkpoint_digest"]
    ):
        raise HistoryChainMismatch(
            "portable writable adoption fast/deep parity refuses",
            deep=deep,
        )

    store = ConceptricStore(
        root,
        read_only=True,
        expected_store_role="live-runtime-fabric",
        authority_context=context,
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    custody = store.verify_custody()
    if custody.get("portable_adoption_grant_root") != adoption["grant_root"]:
        raise HistoryChainMismatch("portable writable custody seal omits its grant root")
    state = store.replay_authority_only()
    if (
        state.event_count != adoption["source_cursor"]
        or state.head_event_id != adoption["source_head_event_id"]
    ):
        raise HistoryChainMismatch("portable writable custody replay moved")

    handles, residuals = _canonical_blob_handles(root / "blobs")
    if residuals:
        raise StoreError(
            "portable writable custody contains noncanonical blob paths",
            paths=residuals[:12],
        )
    blobs = BlobStore(root / "blobs")
    for handle in handles:
        blobs.get(handle)
    blob_root = chash({"handles": list(handles)})
    if (
        len(handles) != int(source_receipt.get("blobs", {}).get("count", -1))
        or blob_root != source_receipt.get("blobs", {}).get("manifest_root")
    ):
        raise StoreError("portable writable custody blob manifest moved")
    required = {record.message.body_handle for record in state.messages.values()}
    missing = tuple(sorted(required - set(handles)))
    source_body_custody = source_receipt.get("message_body_custody")
    if missing:
        if not isinstance(source_body_custody, Mapping):
            raise StoreError("portable writable custody is missing message bodies")
        declaration, _raw, declaration_sha256 = _load_runtime_custody_residual_declaration(
            root / _RUNTIME_CUSTODY_RESIDUAL_NAME
        )
        expected_body_custody = _runtime_message_body_custody(
            state=state,
            available_handles=set(handles),
            declaration=declaration,
            declaration_sha256=declaration_sha256,
        )
        if expected_body_custody != dict(source_body_custody):
            raise StoreError("portable writable message-body residual moved")
    elif source_body_custody is not None:
        raise StoreError("portable writable custody retains a false body residual")

    event_hives = _event_hive_handles(root / "conceptric.sqlite3")
    event_hive_root = chash({"handles": list(event_hives)})
    if (
        len(event_hives) != int(source_receipt.get("event_hives", {}).get("count", -1))
        or event_hive_root != source_receipt.get("event_hives", {}).get("manifest_root")
    ):
        raise StoreError("portable writable custody event-hive manifest moved")
    return {
        "schema_version": "laplace.runtime-atlas-writable-adoption/1",
        "status": "WRITABLE-RECOVERED",
        "snapshot_id": snapshot_id,
        "source_receipt_sha256": source_receipt_sha256,
        "source_ledger_sha256": source_ledger_sha256,
        "grant_root": adoption["grant_root"],
        "grant_identity": adoption["grant_identity"],
        "recovery_coordinate_payload_digest": adoption[
            "recovery_coordinate_payload_digest"
        ],
        "event_count": state.event_count,
        "head_event_id": state.head_event_id,
        "head_record_digest": drift["head_record_digest"],
        "checkpoint_digest": adoption["target_checkpoint_digest"],
        "checkpoint_bytes": int(fast.get("read_metrics", {}).get("checkpoint_bytes", 0)),
        "historical_rows_avoided": int(
            fast.get("read_metrics", {}).get("historical_event_rows_avoided", 0)
        ),
        "custody_receipt_sha256": _file_sha256(root / "hive-custody-receipt.json"),
        "custody_authority_paths_root": custody["authority_paths_root"],
        "custody_grant_root": custody.get("portable_adoption_grant_root"),
        "blob_manifest_root": blob_root,
        "event_hive_manifest_root": event_hive_root,
        "event_append": False,
        "fast_deep_equal": True,
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
        "crutch_id": "CR-C2A-CHECKSUMMED-LIVE-AUTHORITY-20260828",
        "semantic_blueprint_currentness": "UNPAID",
        "remote_publication": "UNPAID",
        "read_only_verification": True,
    }


def _portable_adoption_fault(_phase: str) -> None:
    """No-op crash seam used only by deterministic focused plants."""


def runtime_custody_adoption_grant(
    snapshot_root: str | os.PathLike[str],
    *,
    destination: str | os.PathLike[str],
    recovery_coordinate: str | os.PathLike[str],
) -> dict[str, Any]:
    """Derive, without mutation, the external root a later adoption must be given."""

    source = Path(snapshot_root).expanduser().resolve()
    target = Path(destination).expanduser().resolve()
    verify_runtime_custody(source)
    receipt, receipt_sha256 = _runtime_writable_adoption_source(source)
    target_evidence = ConceptricStore.authority_context_evidence(
        target, store_role="live-runtime-fabric",
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    identity, coordinate_digest, point = _committed_runtime_recovery_grant(
        coordinate_path=recovery_coordinate,
        source_root=source,
        source_receipt=receipt,
        source_receipt_sha256=receipt_sha256,
        destination_root=target,
        destination_context_evidence=target_evidence,
        expected_grant_root=None,
    )
    return {
        "schema_version": "laplace.portable-runtime-adoption-grant-derivation/1",
        "grant_root": chash(identity),
        "grant_identity": identity,
        "coordinate_payload_digest": coordinate_digest,
        "runtime_recovery_point_root": point["point_root"],
        "read_only": True,
        "event_append": False,
    }


def _copy_runtime_capsule_for_adoption(source: Path, pending: Path) -> dict[str, Any]:
    source_before = _runtime_capsule_layout(source)
    if pending.exists():
        try:
            adoption = ConceptricStore.read_portable_authority_adoption(
                pending, expected_store_role="live-runtime-fabric",
                extra_authority_files=EXTRA_AUTHORITY_FILES,
            )
        except (AtlasError, OSError, ValueError):
            adoption = None
        if adoption is not None:
            if _runtime_capsule_layout(source) != source_before:
                raise HistoryChainMismatch("portable adoption source moved before resume")
            return source_before
        try:
            copied = verify_runtime_custody(pending)
        except (AtlasError, OSError, ValueError):
            shutil.rmtree(pending)
        else:
            if copied["snapshot_id"] != json.loads(
                (source / "RECEIPT.json").read_text(encoding="utf-8")
            )["snapshot_id"]:
                raise HistoryChainMismatch("portable adoption pending copy names another snapshot")
            return source_before
    _portable_adoption_fault("before-copy")
    shutil.copytree(source, pending, copy_function=shutil.copy2)
    _portable_adoption_fault("mid-copy")
    source_after = _runtime_capsule_layout(source)
    if source_after != source_before:
        raise HistoryChainMismatch("portable adoption source moved during copy")
    verify_runtime_custody(pending)
    return source_before


def adopt_runtime_custody(
    snapshot_root: str | os.PathLike[str],
    *,
    destination: str | os.PathLike[str],
    recovery_coordinate: str | os.PathLike[str],
    expected_snapshot_id: str,
    expected_grant_root: str,
) -> dict[str, Any]:
    """Copy and explicitly adopt one v2 capsule; the travelling source stays read-only."""

    source = Path(snapshot_root).expanduser().resolve()
    target = Path(destination).expanduser().resolve()
    live_root = store_root().resolve()
    if target == live_root or live_root in target.parents:
        raise StoreError(
            "portable runtime custody adoption refuses the live authority root",
            root=str(target),
        )
    if target == source or source in target.parents or target in source.parents:
        raise StoreError("portable runtime custody source and destination overlap")
    verified_source = verify_runtime_custody(source)
    if verified_source["snapshot_id"] != expected_snapshot_id:
        raise HistoryChainMismatch(
            "portable runtime custody snapshot id moved",
            expected=expected_snapshot_id,
            actual=verified_source["snapshot_id"],
        )
    source_receipt, source_receipt_sha256 = _runtime_writable_adoption_source(source)
    target_context_evidence = ConceptricStore.authority_context_evidence(
        target, store_role="live-runtime-fabric",
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    target_context = dict(target_context_evidence["roots"])
    grant_identity, coordinate_digest, point = _committed_runtime_recovery_grant(
        coordinate_path=recovery_coordinate,
        source_root=source,
        source_receipt=source_receipt,
        source_receipt_sha256=source_receipt_sha256,
        destination_root=target,
        destination_context_evidence=target_context_evidence,
        expected_grant_root=expected_grant_root,
    )
    if target.exists():
        verified = verify_writable_runtime_custody(
            target,
            expected_snapshot_id=expected_snapshot_id,
            expected_grant_root=expected_grant_root,
        )
        return {
            **verified,
            "idempotent": True,
            "ledger_checkpoint_write": False,
            "writer_precondition": "external coordinate/grant + stopped-writer checkpoint CAS",
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name(
        f".{target.name}.adopt-{expected_grant_root.removeprefix('sha256:')[:16]}"
    )
    foreign = [path for path in target.parent.glob(f".{target.name}.adopt-*") if path != pending]
    if foreign:
        raise HistoryChainMismatch(
            "portable adoption found a pending different identity",
            paths=[path.name for path in foreign],
        )
    source_manifest = _copy_runtime_capsule_for_adoption(source, pending)
    existing = ConceptricStore.read_portable_authority_adoption(
        pending, expected_store_role="live-runtime-fabric",
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    if existing is None:
        deep = ConceptricStore.verify_authority_checkpoint_deep(
            pending,
            expected_context=target_context,
            expected_store_role="live-runtime-fabric",
            extra_authority_files=EXTRA_AUTHORITY_FILES,
        )
        if deep.get("verified_predecessor") is None:
            raise HistoryChainMismatch(
                "portable runtime custody source checkpoint is not independently verified",
                deep=deep,
            )
        if deep["verified_predecessor"] != source_receipt["source_checkpoint"][
            "checkpoint_digest"
        ]:
            raise HistoryChainMismatch("portable runtime custody source checkpoint moved")
        non_context = {
            key: value
            for key, value in deep.get("disagreements", {}).items()
            if key not in {"implementation_digest", "environment_root", "dirty_paths_root"}
        }
        if non_context:
            raise HistoryChainMismatch(
                "portable runtime custody source authority disagrees with deep replay",
                disagreements=non_context,
            )
        before = ConceptricStore.read_drift_token(pending, immutable=True)
        _portable_adoption_fault("before-checkpoint-cas")
        prepared = ConceptricStore.prepare_portable_authority_checkpoint(
            pending,
            expected_predecessor=str(deep["verified_predecessor"]),
            authority_context=target_context,
            expected_store_role="live-runtime-fabric",
            source_snapshot_id=expected_snapshot_id,
            source_receipt_sha256=source_receipt_sha256,
            source_ledger_sha256=str(source_receipt["ledger"]["sha256"]),
            source_cursor=int(source_receipt["event_count"]),
            source_head_event_id=source_receipt.get("head_event_id"),
            source_head_record_digest=str(source_receipt["head_record_digest"]),
            source_blob_manifest_root=str(source_receipt["blobs"]["manifest_root"]),
            source_event_hive_manifest_root=str(
                source_receipt["event_hives"]["manifest_root"]
            ),
            source_evidence_manifest_root=str(
                source_receipt["co_resident_evidence"]["manifest_root"]
            ),
            source_authority_context_evidence=dict(
                source_receipt["source_authority_context"]
            ),
            source_git_commit=str(source_receipt["source_git"]["commit"]),
            source_git_tree=str(source_receipt["source_git"]["tree"]),
            recovery_coordinate_payload_digest=coordinate_digest,
            predecessor_adoption_root=str(point["predecessor_adoption_root"]),
            grant_root=expected_grant_root,
            grant_identity=grant_identity,
            target_context_evidence=target_context_evidence,
            target_canonical_root=target,
            extra_authority_files=EXTRA_AUTHORITY_FILES,
        )
        after = ConceptricStore.read_drift_token(pending)
        if before != after:
            raise HistoryChainMismatch(
                "portable runtime custody adoption moved Atlas history",
                before=before,
                after=after,
            )
    else:
        prepared = {**existing, "idempotent": True, "ledger_checkpoint_write": False}
        if (
            existing["source_snapshot_id"] != expected_snapshot_id
            or existing["grant_root"] != expected_grant_root
        ):
            raise HistoryChainMismatch(
                "portable runtime custody adoption retry names another identity"
            )
    _portable_adoption_fault("after-checkpoint-before-reseal")
    ConceptricStore.seal_portable_authority_adoption(
        pending,
        expected_store_role="live-runtime-fabric",
        expected_source_snapshot_id=expected_snapshot_id,
        expected_checkpoint_digest=str(prepared["target_checkpoint_digest"]),
        expected_grant_root=expected_grant_root,
        target_canonical_root=target,
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    _portable_adoption_fault("after-reseal-before-rename")
    verify_writable_runtime_custody(
        pending,
        expected_snapshot_id=expected_snapshot_id,
        expected_grant_root=expected_grant_root,
        canonical_root=target,
    )
    if _runtime_capsule_layout(source) != source_manifest:
        raise HistoryChainMismatch("portable adoption source moved before publication")
    os.replace(pending, target)
    _portable_adoption_fault("after-rename")
    verified = verify_writable_runtime_custody(
        target,
        expected_snapshot_id=expected_snapshot_id,
        expected_grant_root=expected_grant_root,
    )
    return {
        **verified,
        "idempotent": bool(prepared.get("idempotent")),
        "ledger_checkpoint_write": bool(prepared.get("ledger_checkpoint_write")),
        "writer_precondition": "external coordinate/grant + stopped-writer checkpoint CAS",
    }


def _source(
    *,
    body_handle: str | None = None,
    evidence_handles: tuple[str, ...] = (),
) -> tuple[SourceRef, ...]:
    bridge_bytes = Path(__file__).read_bytes()
    refs = [
        SourceRef(
            "laplace.representation.atlas_bridge",
            hash_bytes(bridge_bytes),
            "repo:src/laplace/representation/atlas_bridge.py",
        )
    ]
    if body_handle is not None:
        refs.append(SourceRef("seat-message-body", body_handle, f"blob:{body_handle}"))
    for index, handle in enumerate(dict.fromkeys(evidence_handles), start=1):
        if handle == body_handle:
            continue
        refs.append(SourceRef(f"event-evidence-{index}", handle, f"blob:{handle}"))
    return tuple(refs)


def _residual(note: str) -> Residual:
    return Residual(
        ResidualStatus.WITHIN_BOUND,
        0.0,
        0.0,
        "structural-violations",
        note,
    )


def _producer(provider: str, model: str) -> ProducerRef:
    return ProducerRef(provider, model, "mcp-seat")


def _event(
    kind: EventKind,
    payload: Mapping[str, Any],
    *,
    actor: SeatRole,
    subject: str,
    provider: str,
    model: str,
    correlation_id: str,
    assumption: str | None = None,
    fibre: str | None = None,
    causation_ids: tuple[str, ...] = (),
    body_handle: str | None = None,
    evidence_handles: tuple[str, ...] = (),
    note: str,
    event_residual: Residual | None = None,
    runtime_receipt: RuntimeReceipt | None = None,
) -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at=_now(),
        kind=kind,
        producer=SeatRole.PROVIDER,
        actor=actor,
        subject=subject,
        assumption=assumption,
        fibre=fibre,
        correlation_id=correlation_id,
        causation_ids=causation_ids,
        provenance=_source(
            body_handle=body_handle,
            evidence_handles=evidence_handles,
        ),
        residual=event_residual or _residual(note),
        runtime=runtime_receipt or collect_runtime_receipt(REPO_ROOT),
        producer_ref=_producer(provider, model),
        validity=Validity.VALID,
        payload=dict(payload),
    )


def _receipt(stored: StoredEvent) -> dict[str, Any]:
    return {
        "event_id": stored.event.event_id,
        "sequence": stored.sequence,
        "record_digest": stored.record_digest,
        "kind": stored.event.kind.value,
    }


FRONT_FEEDBACK_ADAPTER_SCHEMA = "laplace.front-feedback-adapter/1"
FRONT_FEEDBACK_EVENT_SCHEMA = "laplace.front-feedback-event/1"
FRONT_FEEDBACK_OBJECT_KIND = FRONT_FEEDBACK_EVENT_SCHEMA


class AtlasFrontFeedbackAdapter:
    """Append-only carrier feedback over the canonical Atlas object history.

    The adapter stores each immutable feedback event as one content-addressed
    ``ConceptricObject`` and uses the verified object-kind frontier as a narrow CAS.
    It owns no shadow journal and grants no authority.
    """

    schema_version = FRONT_FEEDBACK_ADAPTER_SCHEMA

    def __init__(self, store: ConceptricStore | None = None) -> None:
        self._store = store
        self._frontier_root: str | None = None

    def _reader(self) -> ConceptricStore:
        return self._store or _read_store_at(str(store_root()))

    def _writer(self) -> ConceptricStore:
        return self._store or _store_at(str(store_root()))

    def read_events(self) -> tuple[Mapping[str, Any], ...]:
        frontier = self._reader().read_object_kind_frontier(
            kind=FRONT_FEEDBACK_OBJECT_KIND
        )
        self._frontier_root = str(frontier["frontier_root"])
        events: list[Mapping[str, Any]] = []
        for row in frontier["rows"]:
            attributes = row["object"].get("attributes")
            if not isinstance(attributes, Mapping):
                raise HistoryChainMismatch(
                    "front feedback object attributes are malformed",
                    object_id=row["object"].get("object_id"),
                )
            event = attributes.get("event")
            if not isinstance(event, Mapping):
                raise HistoryChainMismatch(
                    "front feedback object omits its canonical event",
                    object_id=row["object"].get("object_id"),
                )
            events.append(dict(event))
        return tuple(events)

    def append_event(self, event: Mapping[str, Any]) -> Mapping[str, Any]:
        # The carrier owns the exact event grammar.  Import lazily so Atlas remains
        # the sole persistence boundary without making front_feedback an Atlas client.
        from laplace.engine.front_feedback import FeedbackRefused, _normalize_event

        try:
            normalized = _normalize_event(event)
            if self._frontier_root is None:
                self.read_events()
            assert self._frontier_root is not None
            item = ConceptricObject(
                object_id=normalized["event_id"],
                kind=FRONT_FEEDBACK_OBJECT_KIND,
                content_handle=normalized["event_handle"],
                assumption=None,
                fibre=None,
                grade_contract_id=CONTROL_AXIS_CONTRACT.contract_id,
                grade_coordinate="content",
                provenance=_source(evidence_handles=(normalized["event_handle"],)),
                attributes={
                    "schema_version": "laplace.front-feedback-atlas-object/1",
                    "event": normalized,
                    "authority_effect": "none",
                },
            )
            atlas_event = _event(
                EventKind.OBJECT,
                item.to_dict(),
                actor=SeatRole.AUTHOR,
                subject=item.object_id,
                provider="laplace-front",
                model="front-feedback-adapter",
                correlation_id=normalized["command_id"],
                evidence_handles=(normalized["event_handle"],),
                note="canonical append-only semantic feedback event",
            )
            stored = self._writer().append_many_if_object_kind_frontier(
                (atlas_event,),
                kind=FRONT_FEEDBACK_OBJECT_KIND,
                expected_frontier_root=self._frontier_root,
            )[0]
            position = {
                "schema_version": "laplace.front-feedback-position/1",
                "event_handle": normalized["event_handle"],
                "atlas_event_id": stored.event.event_id,
                "sequence": stored.sequence,
                "record_digest": stored.record_digest,
            }
            self._frontier_root = None
            return {
                "accepted": True,
                "event_handle": normalized["event_handle"],
                "position_handle": f"front-feedback-position:{chash(position)}",
                "atlas": _receipt(stored),
                "authority_effect": "none",
            }
        except (AtlasError, FeedbackRefused, KeyError, TypeError, ValueError) as exc:
            self._frontier_root = None
            return {
                "accepted": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "authority_effect": "none",
            }


def _descent_identity(
    state: ConceptricState,
    *,
    seat_id: str,
    provider: str,
    model: str,
) -> tuple[str, SeatRole, str, str]:
    """Resolve the logical caller without turning a missing provider binding into a lie."""

    seat = seat_id.strip() or os.environ.get("LAPLACE_SEAT_ID", "").strip()
    if not seat and os.environ.get("CODEX_THREAD_ID"):
        seat = "codex-seat"
    if not seat and (os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("CLAUDE_SESSION_ID")):
        seat = "claude-seat"
    if seat:
        actor = _seat_role(state, seat)
    else:
        seat, actor = "system", SeatRole.SYSTEM
    inferred_provider = (
        "codex"
        if seat == "codex-seat"
        else "claude"
        if seat in {"claude-seat", "interface-seat"}
        else "local"
    )
    return (
        seat,
        actor,
        provider.strip() or inferred_provider,
        model.strip() or os.environ.get("LAPLACE_MODEL_ID", "unknown"),
    )


def begin_typed_descent(
    *,
    kind: str,
    reference: str,
    source: str,
    goal: str,
    seat_id: str = "",
    provider: str = "",
    model: str = "",
    correlation_id: str = "",
) -> dict[str, Any]:
    """Bank the call edge before an exact resolver runs.

    The control axis is already part of every Atlas state.  A typed read moves from its
    reconstruction boundary into the requested content boundary; the later materialization
    event causally records what returned.  No parallel telemetry ledger is introduced.
    """

    import time

    store = _store()
    state = store.current_state()
    assumption, fibre = _context(state)
    seat, actor, provider_name, model_name = _descent_identity(
        state, seat_id=seat_id, provider=provider, model=model
    )
    resolved_goal = goal.strip() or f"resolve exact {kind} reference {reference}"
    correlation = _correlation(
        correlation_id or os.environ.get("LAPLACE_CORRELATION_ID", ""),
        {
            "goal": resolved_goal,
            "seat": seat,
            "session": os.environ.get("LAPLACE_SESSION", "process"),
        },
    )
    started_ns = time.monotonic_ns()
    movement_id = "movement:" + chash(
        {
            "correlation": correlation,
            "kind": kind,
            "reference": reference,
            "source": source,
            "started_ns": started_ns,
        }
    ).removeprefix("sha256:")
    goal_handle = chash({"goal": resolved_goal, "correlation": correlation})
    node_handle = chash({"kind": kind, "reference": reference, "source": source})
    provenance = (
        SourceRef(
            "laplace.typed-descent",
            hash_bytes((REPO_ROOT / "src" / "laplace" / "engine" / "descent.py").read_bytes()),
            "repo:src/laplace/engine/descent.py",
        ),
    )
    pending = Residual(
        ResidualStatus.UNKNOWN,
        None,
        None,
        "typed-descent-return",
        "the exact resolver has been entered and has not returned yet",
    )
    runtime_receipt = collect_runtime_receipt(REPO_ROOT)
    movement = Movement(
        movement_id,
        MoveDirection.DOWN,
        resolved_goal,
        f"laplace.typed-descent/1:{kind}",
        BoundaryRef(goal_handle, "goal:" + goal_handle.removeprefix("sha256:"), assumption, fibre),
        BoundaryRef(
            reference, "typed-reference:" + node_handle.removeprefix("sha256:"), assumption, fibre
        ),
        GradeAxis(
            CONTROL_AXIS_CONTRACT.contract_id,
            CONTROL_AXIS_CONTRACT.axis,
            "reconstruction",
            "content",
        ),
        provenance,
        pending,
        False,
        "materialize the exact typed resolver return or typed refusal",
    )
    event = _event(
        EventKind.MOVE,
        movement.to_dict(),
        actor=actor,
        subject=movement.target.node_id,
        provider=provider_name,
        model=model_name,
        correlation_id=correlation,
        assumption=assumption,
        fibre=fibre,
        causation_ids=() if state.head_event_id is None else (state.head_event_id,),
        note=pending.note,
        event_residual=pending,
        runtime_receipt=runtime_receipt,
    )
    stored = store.append(event)
    return {
        "schema_version": "laplace.engine.descent-trace/1",
        "status": "MOVED",
        "seat_id": seat,
        "actor": actor.value,
        "kind": kind,
        "reference": reference,
        "source": source,
        "goal": resolved_goal,
        "assumption": assumption,
        "fibre": fibre,
        "correlation_id": correlation,
        "movement_id": movement_id,
        "movement_receipt": _receipt(stored),
        "_started_ns": started_ns,
        "_actor": actor,
        "_provider": provider_name,
        "_model": model_name,
        "_runtime": runtime_receipt,
        "_store": store,
    }


def finish_typed_descent(
    trace: Mapping[str, Any],
    *,
    result_handle: str,
    provenance: Mapping[str, Any],
    refused: str = "",
) -> dict[str, Any]:
    """Bank the exact return causally after its movement and return a public trace receipt."""

    import time

    failed = bool(refused)
    residual = Residual(
        ResidualStatus.EXCEEDS_BOUND if failed else ResidualStatus.WITHIN_BOUND,
        1.0 if failed else 0.0,
        0.0,
        "typed-descent-refusals",
        refused or "the exact typed resolver returned a content-addressed result",
    )
    movement_receipt = dict(trace["movement_receipt"])
    movement_id = str(trace["movement_id"])
    materialization_id = "materialization:" + chash(
        {
            "movement_id": movement_id,
            "result_handle": result_handle,
            "refused": refused,
        }
    ).removeprefix("sha256:")
    corpus_root = chash(
        {
            "kind": trace["kind"],
            "source": trace["source"],
        }
    )
    materialized = MaterializedReconstruction(
        materialization_id,
        str(trace["goal"]),
        str(trace["assumption"]),
        str(trace["fibre"]),
        "laplace.typed-descent/1 exact typed resolver; no semantic substitution",
        {str(trace["kind"]): corpus_root},
        str(trace["reference"]),
        (movement_id,),
        (result_handle,),
        {
            "movement_event": str(movement_receipt["event_id"]),
            "reference": chash(
                {
                    "kind": trace["kind"],
                    "reference": trace["reference"],
                    "source": trace["source"],
                }
            ),
            "result_provenance": chash(dict(provenance)),
        },
        residual,
        0.0 if failed else 1.0,
    )
    event = _event(
        EventKind.MATERIALIZATION,
        materialized.to_dict(),
        actor=trace["_actor"],
        subject=materialization_id,
        provider=str(trace["_provider"]),
        model=str(trace["_model"]),
        correlation_id=str(trace["correlation_id"]),
        assumption=str(trace["assumption"]),
        fibre=str(trace["fibre"]),
        causation_ids=(str(movement_receipt["event_id"]),),
        note=residual.note,
        event_residual=residual,
        runtime_receipt=trace["_runtime"],
    )
    stored = trace["_store"].append(event)
    duration_ms = (time.monotonic_ns() - int(trace["_started_ns"])) / 1_000_000
    return {key: value for key, value in trace.items() if not str(key).startswith("_")} | {
        "status": "REFUSED" if failed else "MATERIALIZED",
        "materialization_id": materialization_id,
        "materialization_receipt": _receipt(stored),
        "duration_ms": round(duration_ms, 3),
        "refused": refused or None,
    }


def _context(state: ConceptricState) -> tuple[str, str]:
    if state.active_assumption is None or state.active_fibre is None:
        raise StateTransitionRefused("seat act requires an explicitly selected assumption fibre")
    return state.active_assumption, state.active_fibre


def _seat_role(state: ConceptricState, seat_id: str) -> SeatRole:
    seat = state.seats.get(seat_id)
    if seat is None or seat.status == SeatStatus.CLOSED:
        raise StateTransitionRefused("logical seat is not live", seat_id=seat_id)
    return SeatRole(seat.role)


def _correlation(explicit: str, seed: Mapping[str, Any]) -> str:
    return explicit.strip() or "correlation:" + chash(seed).removeprefix("sha256:")[:24]


def _parsed_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _watch_event_matches(event: AtlasEvent, selector: Mapping[str, Any]) -> bool:
    event_kind = selector.get("event_kind")
    subject_prefix = selector.get("subject_prefix")
    correlation_id = selector.get("correlation_id")
    return (
        (event_kind is None or event.kind.value == event_kind)
        and (subject_prefix is None or event.subject.startswith(str(subject_prefix)))
        and (correlation_id is None or event.correlation_id == correlation_id)
    )


def _filesystem_observation(path: Path) -> str | None:
    """Return a content address for path metadata, never the watched file's content."""

    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return chash(
        {
            "path": os.fspath(path),
            "kind": "directory" if path.is_dir() else "file",
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    )


def drift_token() -> dict[str, Any]:
    """Return an O(1), migration-stable invalidation token for Atlas readers.

    The compact tip does not replay or certify the history.  A consumer may use it only to decide
    whether a projection it previously built and verified is still current.
    """

    return ConceptricStore.read_drift_token(store_root())


def development_review_frontier(*, terminal_cap: int = 6) -> dict[str, Any]:
    """Read the replaceable published-work frontier from the head-bound Atlas index.

    This deliberately bypasses ``provider_snapshot``: closed message history is not wake
    context.  The ledger remains the authority and the projection refuses unless it names the
    exact compact ledger head.
    """

    return ConceptricStore.read_development_review_frontier(
        store_root(), terminal_cap=terminal_cap, observed_at=_now()
    )


def seat_mail_observation(
    *,
    seat_id: str,
    previous_mail_token: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read one recipient's head-bound pending frontier without global materialisation."""

    return ConceptricStore.read_seat_mail_frontier(
        store_root(),
        seat_id=seat_id,
        previous_mail_token=previous_mail_token,
        expected_context=_authority_epoch_context(store_root()),
    )


def provider_seat_binding(*, provider_session_ref: str) -> dict[str, Any]:
    """Resolve one provider task through the head-bound occupancy projection."""

    return ConceptricStore.read_provider_seat_binding(
        store_root(),
        provider_session_ref=provider_session_ref,
        expected_context=_authority_epoch_context(store_root()),
    )


def authority_epoch() -> dict[str, Any]:
    """Read the head-bound checksummed checkpoint; never deep-replay as fallback."""

    return ConceptricStore.read_authority_checkpoint(
        store_root(), expected_context=_authority_epoch_context(store_root()),
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )


def atlas_object(*, reference: str, observed_at: str | None = None) -> dict[str, Any]:
    """Read one exact Atlas object through the CURRENT checksummed authority epoch."""

    root = store_root()
    return ConceptricStore.read_atlas_object(
        root,
        reference=reference,
        expected_context=_authority_epoch_context(root),
        observed_at=observed_at,
    )


def verify_atlas_object_current_root(
    *, reference: str, expected_current_root: str
) -> dict[str, Any]:
    """Pure JIT current-root equality check; no provider snapshot, prepare, or write."""

    root = store_root()
    return ConceptricStore.verify_atlas_object_current_root(
        root,
        reference=reference,
        expected_current_root=expected_current_root,
        expected_context=_authority_epoch_context(root),
    )


def inspect_authority_epoch() -> dict[str, Any]:
    """Deeply reconstruct the stopped-writer predecessor/candidate parity receipt."""

    receipt = ConceptricStore.verify_authority_checkpoint_deep(
        store_root(), expected_context=_authority_epoch_context(store_root()),
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    return {
        **receipt,
        "schema_version": "laplace.authority-epoch-inspection/1",
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
        "event_append": False,
        "writer_precondition": "STOPPED",
    }


def prepare_authority_epoch(
    *, expected_predecessor: str | None = None, root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Explicit stopped-writer C2 adoption; readers never invoke this transition."""

    default_root = root is None
    root = (store_root() if default_root else Path(root)).expanduser().resolve()
    if dry_run:
        wal = root / "conceptric.sqlite3-wal"
        if wal.is_file() and wal.stat().st_size:
            raise StoreError("dry-run authority adoption requires a checkpointed WAL")
    reader = ConceptricStore(
        root, read_only=True, immutable=dry_run,
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    with reader._locked(shared=True), reader._connect() as connection:
        identities = [json.loads(row["value"]) for row in connection.execute(
            "SELECT value FROM meta WHERE key IN "
            "('store_identity_json', 'store_role_anchor_json')"
        )]
    if not identities:
        raise StoreError("authority adoption requires an existing store role anchor")
    for identity in identities:
        reader._validate_store_identity(identity, operation="authority adoption")
    if any(identity != identities[0] for identity in identities):
        raise StoreError("authority adoption store identity and role anchor disagree")
    role = identities[0]["role"]
    if default_root and role != "live-runtime-fabric":
        raise StoreError("default runtime authority adoption role disagrees", store_role=role)
    reachability = reader.hive_reachability()
    reader._require_exact_reachability(reachability)
    context = ConceptricStore.authority_context_manifest(
        root, store_role=role, extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    inspection = ConceptricStore.verify_authority_checkpoint_deep(
        root, expected_context=context, expected_store_role=role,
        extra_authority_files=EXTRA_AUTHORITY_FILES, immutable=dry_run,
    )
    predecessor = inspection.get("verified_predecessor")
    if not predecessor:
        raise StoreError("authority adoption predecessor verification refused", inspection=inspection)
    if expected_predecessor is not None and expected_predecessor != predecessor:
        raise StoreError("authority adoption predecessor moved",
                         expected=expected_predecessor, actual=predecessor)
    if dry_run:
        return {
            "schema_version": "laplace.authority-epoch-preview/1",
            "status": "DRY-RUN", "store": os.fspath(root), "store_role": role,
            "expected_predecessor": predecessor,
            "checkpoint": inspection["candidate_checkpoint"],
            "checkpoint_digest": inspection["candidate_checkpoint_digest"],
            "authority_context": context, "event_append": False,
            "reachability_status": reachability["status"],
            "ledger_checkpoint_write": False,
            "would_bank": "atlas.authority-checkpoint-adoption/1",
        }
    _store_at.cache_clear()
    _read_store_at.cache_clear()
    prepared = ConceptricStore.prepare_authority_checkpoint(
        root,
        expected_predecessor=predecessor,
        expected_store_role=role,
        authority_context=context,
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    verified = ConceptricStore.read_authority_checkpoint(
        root, expected_context=context,
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    if verified["status"] != "CURRENT":
        raise StoreError("prepared authority checkpoint did not verify", verification=verified)
    _store_at.cache_clear()
    _read_store_at.cache_clear()
    return {
        "schema_version": "laplace.authority-epoch-preparation/1",
        "status": "READY",
        "checkpoint_digest": prepared["checkpoint_digest"],
        "receipt_handle": prepared["receipt_handle"],
        "receipt_key": prepared["receipt_key"],
        "expected_predecessor": predecessor,
        "store_role": role,
        "cursor": verified["checkpoint"]["cursor"],
        "head_record_digest": verified["checkpoint"]["head_record_digest"],
        "history_replay_boundary": "explicit stopped-writer adoption only",
        "event_append": False,
        "ledger_checkpoint_write": True,
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
        "crutch_id": "CR-C2A-CHECKSUMMED-LIVE-AUTHORITY-20260828",
        "writer_precondition": "exclusive store lock; stopped-writer adoption",
        "store": os.fspath(root),
    }


def prepare_seat_mail_projection() -> dict[str, Any]:
    """Complete the disposable schema transition before any new watcher reader starts."""

    _store_at.cache_clear()
    _read_store_at.cache_clear()
    prepared = ConceptricStore.prepare_seat_mail_projection(store_root())
    _store_at.cache_clear()
    _read_store_at.cache_clear()
    return {
        **prepared,
        "schema_version": "laplace.seat-mail-projection-transition/1",
        "authority_write": False,
        "runtime_activated": False,
    }


def provider_observation(
    *,
    previous_token: Mapping[str, Any] | None = None,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Return a stable provider projection only when the causal tip moved.

    Watchers need to answer two different questions at radically different costs:
    ``did Atlas move?`` and ``what does the whole provider state now mean?``.  The old
    loops answered both by replaying/materialising the provider face on every poll.  A
    drift token is an invalidator, not a verification receipt, so it may skip an
    unchanged projection but may never stand in for one after movement.

    The token brackets the materialisation.  If a writer lands between the two reads,
    retry against the new tip rather than caching a projection under a head it may not
    contain.  A write immediately after the closing read is harmless: the next poll sees
    the new token.  Thus the cheap path cannot swallow an event at the race seam.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")

    token = drift_token()
    if previous_token is not None and dict(previous_token) == token:
        return {
            "schema_version": "laplace.atlas-provider-observation/1",
            "changed": False,
            "drift_token": token,
            "provider": None,
            "materialization_attempts": 0,
            "read_only": True,
        }

    for attempt in range(1, max_attempts + 1):
        before = token
        provider = _read_store().provider_snapshot(observed_at=_now())
        after = drift_token()
        if before == after:
            return {
                "schema_version": "laplace.atlas-provider-observation/1",
                "changed": True,
                "drift_token": after,
                "provider": provider,
                "materialization_attempts": attempt,
                "read_only": True,
            }
        token = after

    raise StoreError(
        "Atlas moved throughout provider observation; no stable projection was cached",
        attempts=max_attempts,
        last_cursor=token.get("cursor"),
        last_head_event_id=token.get("head_event_id"),
    )


def snapshot() -> dict[str, Any]:
    """Return the provider face without founding or repairing an absent authority."""

    view = _read_store().provider_snapshot(observed_at=_now())
    return {
        "schema_version": BRIDGE_SCHEMA,
        "store_root": str(store_root()),
        "provider": view,
    }


def event_history_projection(event_ids: Iterable[str]) -> dict[str, Any]:
    """Exact-resolve a bounded set of events through the verified Atlas history.

    A provider snapshot is a current fold, not evidence that an arbitrary predecessor ever
    existed.  Recovery/succession checks need the latter without importing Atlas outside this
    allowlisted bridge.  ``ConceptricStore.events`` verifies the complete append-only chain and
    every hived event before this function selects the requested rows, so an absent id remains
    absent and cannot be laundered by a plausible payload supplied by the caller.
    """

    wanted = tuple(dict.fromkeys(str(event_id) for event_id in event_ids if str(event_id)))
    selected: dict[str, dict[str, Any]] = {}
    for sequence, event in enumerate(_read_store().events(), start=1):
        if event.event_id not in wanted:
            continue
        selected[event.event_id] = {
            "event_id": event.event_id,
            "sequence": sequence,
            "kind": event.kind.value,
            "actor": event.actor.value,
            "subject": event.subject,
            "assumption": event.assumption,
            "fibre": event.fibre,
            "causation_ids": list(event.causation_ids),
            "payload": dict(event.payload),
        }
    return {
        "schema_version": "laplace.atlas-event-history-projection/1",
        "requested_event_ids": list(wanted),
        "events": selected,
        "missing_event_ids": sorted(set(wanted) - set(selected)),
        "read_only": True,
        "proof_boundary": "fully verified canonical Atlas event history",
    }


def message_body(*, message_id: str) -> dict[str, Any]:
    """Resolve one exact fabric body without changing pull or delivery state.

    This is a read descent for a warranted projection.  It deliberately does not move the
    recipient cursor and can never stand in for reconstruction or acknowledgement.
    """

    record = _read_store().current_state().messages.get(message_id)
    if record is None:
        raise StateTransitionRefused("body descent cites unknown message", message_id=message_id)
    body = _blobs().get(record.message.body_handle).decode("utf-8")
    return {
        "schema_version": "laplace.atlas-message-body/1",
        "message_id": message_id,
        "body_handle": record.message.body_handle,
        "media_type": BODY_MEDIA_TYPE,
        "body": body,
        "read_only": True,
        "storage_access": "sqlite mode=ro/query_only; bounded shared flock; authority writes none",
        "delivery_claim": "none",
        "dependency_freshness": _message_dependency_freshness(record.message.dependency_roots),
    }


def mail_obligations(*, seat_id: str) -> dict[str, Any]:
    """Serve recipient-scoped queued and pulled nonterminal obligations from Atlas itself.

    A durable cursor can make ``pull`` return an empty inbox while earlier messages remain
    PULLED and unacknowledged.  This face reads the canonical message states rather than a side
    ledger, includes every fibre, and says which obligations are reconstructable in the active
    context.  It performs no pull, reconstruction, acknowledgement, or context transport.
    """

    store = _read_store()
    state = store.current_state()
    _seat_role(state, seat_id)
    assumption, fibre = _context(state)
    blobs = BlobStore(store.root / "blobs")
    obligations = []
    for message_id, record in state.messages.items():
        message = record.message
        if message.recipient_seat_id != seat_id or record.status.value not in {"queued", "pulled"}:
            continue
        try:
            blobs.get(message.body_handle)
            content_state, content_error = "READABLE", None
        except (BlobMissing, BlobHashMismatch) as exc:
            content_state = "UNKNOWN"
            content_error = f"{type(exc).__name__}: {exc}"
        context_matches = (record.assumption, record.fibre) == (assumption, fibre)
        obligations.append(
            {
                "message_id": message_id,
                "cursor": message.cursor,
                "sender_seat_id": message.sender_seat_id,
                "recipient_seat_id": message.recipient_seat_id,
                "message_type": message.message_type,
                "body_handle": message.body_handle,
                "status": record.status.value,
                "assumption": record.assumption,
                "fibre": record.fibre,
                "context_matches": context_matches,
                "reconstructable_in_active_context": (
                    context_matches
                    and record.status.value == "pulled"
                    and content_state == "READABLE"
                ),
                "content_state": content_state,
                "content_error": content_error,
                "dependency_freshness": _message_dependency_freshness(message.dependency_roots),
            }
        )
    obligations.sort(key=lambda row: (row["cursor"], row["message_id"]))
    current = [row for row in obligations if row["context_matches"]]
    foreign = [row for row in obligations if not row["context_matches"]]
    return {
        "schema_version": "laplace.fabric-mail-obligations/1",
        "seat_id": seat_id,
        "active_context": {"assumption": assumption, "fibre": fibre},
        "obligations": obligations,
        "counts": {
            "total": len(obligations),
            "queued": sum(row["status"] == "queued" for row in obligations),
            "pulled": sum(row["status"] == "pulled" for row in obligations),
            "current_context": len(current),
            "other_context": len(foreign),
            "unknown_content": sum(row["content_state"] == "UNKNOWN" for row in obligations),
        },
        "read_only": True,
        "delivery_claim": "none",
    }


def _git_resolve_commit(reference: str) -> str | None:
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", f"{reference}^{{commit}}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return resolved.stdout.strip() if resolved.returncode == 0 else None


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _git_head() -> str:
    head = _git_resolve_commit("HEAD")
    if head is None:
        raise StoreError("repository HEAD does not resolve to a commit")
    return head


def _git_dirty_paths() -> tuple[str, ...]:
    observed = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if observed.returncode != 0:
        raise StoreError(
            "Git worktree status could not be observed",
            error=observed.stderr.decode("utf-8", errors="replace"),
        )
    fields = observed.stdout.split(b"\0")
    paths: set[str] = set()
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if not field:
            continue
        status = field[:2].decode("ascii", errors="replace")
        paths.add(field[3:].decode("utf-8", errors="surrogateescape"))
        if status[:1] in {"R", "C"} and index < len(fields) and fields[index]:
            paths.add(fields[index].decode("utf-8", errors="surrogateescape"))
            index += 1
    return tuple(sorted(paths))


def _git_staged_paths() -> tuple[str, ...]:
    """Return the exact index delta without conflating it with worktree dirt."""

    observed = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if observed.returncode != 0:
        raise StoreError(
            "Git index state could not be observed",
            error=observed.stderr.decode("utf-8", errors="replace"),
        )
    return tuple(
        sorted(
            path.decode("utf-8", errors="surrogateescape")
            for path in observed.stdout.split(b"\0")
            if path
        )
    )


def _git_stage_regions(regions: tuple[str, ...]) -> None:
    observed = subprocess.run(
        ["git", "add", "-A", "--", *regions],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if observed.returncode != 0:
        raise StoreError(
            "Git could not stage the leased regions",
            regions=list(regions),
            error=observed.stderr.decode("utf-8", errors="replace"),
        )


def _git_commit_leased_candidate(*, message: str, lease_id: str, holder_ref: str) -> str:
    """Commit the prepared index with boundary-owned exact attribution trailers."""

    summary = message.strip()
    if not summary:
        raise StateTransitionRefused("region publication requires a commit message")
    if re.search(r"^Laplace-(?:Lease|Holder):", summary, re.MULTILINE):
        raise StateTransitionRefused(
            "region publication owns the lease and holder trailers; callers cannot supply them"
        )
    commit_message = f"{summary}\n\nLaplace-Lease: {lease_id}\nLaplace-Holder: {holder_ref}\n"
    # This commit is the authority boundary itself. Repository hooks run after the
    # staged candidate was measured and can replace or restage its content; --no-verify
    # does not suppress every commit hook. An explicit empty hooksPath keeps the exact
    # measured index authoritative while caller-supplied verification remains evidence.
    with tempfile.TemporaryDirectory(prefix="laplace-empty-hooks-") as empty_hooks:
        observed = subprocess.run(
            [
                "git",
                "-c",
                f"core.hooksPath={empty_hooks}",
                "commit",
                "--quiet",
                "--file=-",
            ],
            cwd=REPO_ROOT,
            input=commit_message,
            capture_output=True,
            text=True,
            check=False,
        )
    if observed.returncode != 0:
        raise StoreError(
            "Git could not publish the leased candidate",
            error=observed.stderr,
        )
    return _git_head()


def _git_bytes(
    arguments: list[str],
    *,
    environment: Mapping[str, str] | None = None,
    input_bytes: bytes | None = None,
) -> bytes:
    observed = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        env=None if environment is None else dict(environment),
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if observed.returncode != 0:
        raise StoreError(
            "Git publication operation refused",
            operation=arguments[0] if arguments else "git",
            error=observed.stderr.decode("utf-8", errors="replace"),
        )
    return observed.stdout


def _git_ref_oid(base_ref: str) -> str:
    ref = str(base_ref).strip()
    if not ref.startswith("refs/heads/") or any(character.isspace() for character in ref):
        raise StateTransitionRefused(
            "local publication base ref must be an exact refs/heads/... name"
        )
    return _git_bytes(["rev-parse", "--verify", f"{ref}^{{commit}}"] ).decode().strip()


def _publication_sha256(value: str, *, field: str) -> str:
    normalized = str(value).strip()
    if (
        len(normalized) != 71
        or not normalized.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in normalized[7:])
    ):
        raise StateTransitionRefused(
            "publication authority root must be an exact sha256 handle", field=field
        )
    return normalized


def _main_index_receipt() -> dict[str, Any]:
    raw = _git_bytes(["rev-parse", "--git-path", "index"]).decode().strip()
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    data = path.read_bytes() if path.is_file() else b""
    return {"exists": path.is_file(), "bytes": len(data), "handle": hash_bytes(data)}


def _private_index_candidate(
    *,
    checkout: RegionCheckout,
    base_ref: str,
    message: str,
    evidence: Mapping[str, str],
) -> dict[str, Any]:
    """Build one unreachable commit from a private index without moving any ref/index."""

    summary = message.strip()
    if not summary:
        raise StateTransitionRefused("publication prepare requires a commit message")
    if re.search(r"^Laplace-(?:Lease|Holder):", summary, re.MULTILINE):
        raise StateTransitionRefused("publication prepare owns its attribution trailers")
    expected_old = _git_ref_oid(base_ref)
    if _git_is_ancestor(expected_old, checkout.base_git_head):
        candidate_parent = checkout.base_git_head
    elif _git_is_ancestor(checkout.base_git_head, expected_old):
        candidate_parent = expected_old
    else:
        raise StateTransitionRefused(
            "publication base ref and lease checkout diverged",
            checkout_head=checkout.base_git_head,
            expected_old=expected_old,
        )
    index_before = _main_index_receipt()
    recipe = {
        "schema_version": "laplace.private-git-index-recipe/1",
        "index_scope": "ephemeral-private",
        "base_ref": base_ref,
        "expected_old": expected_old,
        "candidate_parent": candidate_parent,
        "regions": list(checkout.regions),
        "commands": ["read-tree", "add -A -- <regions>", "write-tree", "commit-tree"],
    }
    with tempfile.TemporaryDirectory(prefix="laplace-publication-index-") as directory:
        index_path = Path(directory) / "index"
        environment = {**os.environ, "GIT_INDEX_FILE": os.fspath(index_path)}
        _git_bytes(["read-tree", candidate_parent], environment=environment)
        _git_bytes(["add", "-A", "--", *checkout.regions], environment=environment)
        candidate_tree = _git_bytes(["write-tree"], environment=environment).decode().strip()
        changed_raw = _git_bytes(
            ["diff", "--name-only", "-z", candidate_parent, candidate_tree]
        )
        committed_paths = tuple(
            sorted(
                path.decode("utf-8", errors="surrogateescape")
                for path in changed_raw.split(b"\0")
                if path
            )
        )
        if not committed_paths:
            raise StateTransitionRefused("publication prepare produced an empty candidate")
        escaped = tuple(
            path
            for path in committed_paths
            if not _path_in_regions(path, checkout.regions)
        )
        if escaped:
            raise StateTransitionRefused(
                "private publication candidate escaped its lease", paths=list(escaped)
            )
        commit_message = (
            f"{summary}\n\nLaplace-Lease: {checkout.lease_id}\n"
            f"Laplace-Holder: {checkout.holder_ref}\n"
        ).encode("utf-8")
        candidate_commit = _git_bytes(
            ["commit-tree", candidate_tree, "-p", candidate_parent],
            environment=environment,
            input_bytes=commit_message,
        ).decode().strip()
        if not _git_is_ancestor(expected_old, candidate_commit):
            raise StateTransitionRefused(
                "publication candidate does not descend from its CAS predecessor",
                expected_old=expected_old,
                candidate_parent=candidate_parent,
                candidate_commit=candidate_commit,
            )
    index_after = _main_index_receipt()
    if index_after != index_before:
        raise StateTransitionRefused(
            "private publication candidate moved the main Git index",
            before=index_before,
            after=index_after,
        )
    patch = _git_bytes(
        [
            "diff",
            "--binary",
            "--full-index",
            candidate_parent,
            candidate_tree,
            "--",
            *checkout.regions,
        ]
    )
    patch_handle = _blobs().put(patch)
    custody = {
        "schema_version": "laplace.region-publication-custody/1",
        "lease_id": checkout.lease_id,
        "base_ref": base_ref,
        "expected_old": expected_old,
        "candidate_parent": candidate_parent,
        "candidate_tree": candidate_tree,
        "candidate_commit": candidate_commit,
        "committed_paths": list(committed_paths),
        "patch_handle": patch_handle,
        "private_index_recipe": recipe,
        "main_index_receipt": index_before,
        "evidence": dict(evidence),
    }
    custody_handle = _blobs().put((canonical_json(custody) + "\n").encode("utf-8"))
    return {
        **custody,
        "custody_handle": custody_handle,
    }


def _git_update_ref_once(*, base_ref: str, expected_old: str, candidate_commit: str) -> str:
    observed = _git_ref_oid(base_ref)
    if observed == candidate_commit:
        return "ALREADY-APPLIED"
    if observed != expected_old:
        raise StateTransitionRefused(
            "publication ref moved outside its authorized CAS",
            state="REFUSED",
            base_ref=base_ref,
            expected_old=expected_old,
            observed=observed,
            candidate_commit=candidate_commit,
        )
    _git_bytes(
        ["update-ref", "--no-deref", base_ref, candidate_commit, expected_old]
    )
    return "CAS-APPLIED"


def _git_changed_paths(base: str, result: str) -> tuple[str, ...]:
    observed = subprocess.run(
        ["git", "diff", "--name-only", "-z", f"{base}..{result}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if observed.returncode != 0:
        raise StoreError(
            "Git could not derive the checkin delta",
            base=base,
            result=result,
            error=observed.stderr.decode("utf-8", errors="replace"),
        )
    return tuple(
        sorted(
            path.decode("utf-8", errors="surrogateescape")
            for path in observed.stdout.split(b"\0")
            if path
        )
    )


def _path_in_regions(path: str, regions: tuple[str, ...]) -> bool:
    return any(path == region or path.startswith(region + "/") for region in regions)


def _git_commits_between(base: str, result: str) -> tuple[str, ...]:
    observed = subprocess.run(
        ["git", "rev-list", "--reverse", f"{base}..{result}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if observed.returncode != 0:
        raise StoreError(
            "Git could not enumerate commits for holder attribution",
            base=base,
            result=result,
            error=observed.stderr,
        )
    return tuple(line.strip() for line in observed.stdout.splitlines() if line.strip())


def _git_commit_message(commit: str) -> str:
    observed = subprocess.run(
        ["git", "show", "-s", "--format=%B", commit],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if observed.returncode != 0:
        raise StoreError(
            "Git could not read a commit for holder attribution",
            commit=commit,
            error=observed.stderr,
        )
    return observed.stdout


def _git_commit_paths(commit: str) -> tuple[str, ...]:
    observed = subprocess.run(
        [
            "git",
            "diff-tree",
            "--root",
            "-m",
            "--no-commit-id",
            "--name-only",
            "-r",
            "-z",
            commit,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if observed.returncode != 0:
        raise StoreError(
            "Git could not read commit paths for holder attribution",
            commit=commit,
            error=observed.stderr.decode("utf-8", errors="replace"),
        )
    return tuple(
        sorted(
            {
                path.decode("utf-8", errors="surrogateescape")
                for path in observed.stdout.split(b"\0")
                if path
            }
        )
    )


def _git_holder_attribution(
    *,
    base: str,
    result: str,
    lease_id: str,
    holder_ref: str,
    regions: tuple[str, ...],
) -> dict[str, Any]:
    """Attribute in-scope commits to a lease through exact Git trailers.

    A commit may move concurrently outside the lease.  Any commit touching the
    leased scope must carry both ``Laplace-Lease`` and ``Laplace-Holder`` exact
    trailers; otherwise a checkin would credit another actor's delta.
    """

    attributed: list[str] = []
    attributed_paths: set[str] = set()
    attributed_paths_outside_scope: set[str] = set()
    concurrent_paths_outside_scope: set[str] = set()
    unattributed_paths: set[str] = set()
    for commit in _git_commits_between(base, result):
        paths = _git_commit_paths(commit)
        in_scope = {path for path in paths if _path_in_regions(path, regions)}
        if not in_scope:
            concurrent_paths_outside_scope.update(paths)
            continue
        outside_scope = set(paths) - in_scope
        message = _git_commit_message(commit)
        lease_matches = re.findall(r"^Laplace-Lease:\s*(\S+)\s*$", message, re.MULTILINE)
        holder_matches = re.findall(r"^Laplace-Holder:\s*(\S+)\s*$", message, re.MULTILINE)
        if lease_matches == [lease_id] and holder_matches == [holder_ref]:
            attributed.append(commit)
            attributed_paths.update(in_scope)
            attributed_paths_outside_scope.update(outside_scope)
        else:
            unattributed_paths.update(in_scope)
    return {
        "schema_version": "laplace.git-holder-attribution/2",
        "lease_id": lease_id,
        "holder_ref": holder_ref,
        "attributed_commits": attributed,
        "attributed_paths": sorted(attributed_paths),
        "attributed_paths_outside_scope": sorted(attributed_paths_outside_scope),
        "concurrent_paths_outside_scope": sorted(concurrent_paths_outside_scope),
        "unattributed_paths": sorted(unattributed_paths),
        "required_trailers": {
            "Laplace-Lease": lease_id,
            "Laplace-Holder": holder_ref,
        },
    }


def _known_coordinate_payload_digests() -> set[str]:
    """Return only payloads that exist as integrity-valid recovery packet artifacts."""

    from laplace.representation.recovery_coordinate import canonical_payload_digest

    known: set[str] = set()
    packet_root = REPO_ROOT / "atlas" / "packets" / "recovery"
    for path in packet_root.glob("RECOVERY-COORDINATE*.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            actual = canonical_payload_digest(document)
            if actual == document.get("coordinate_payload_digest"):
                known.add(actual)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return known


def _dependency_freshness(dependency_roots: Mapping[str, str]) -> dict[str, Any]:
    """Recompute recognised live roots while leaving opaque application roots untouched.

    This is an observation, not a gate: stale messages still travel so the recipient can judge
    them, but the message face can no longer make an aged root look current by omission.
    Expensive blueprint replay is intentionally not hidden in every send; that recognised kind is
    rendered ``UNMEASURED`` until it gets an O(1) drift token.
    """

    roots = {
        str(key): str(value)
        for key, value in dependency_roots.items()
        if key != _DEPENDENCY_FRESHNESS_ROOT
    }
    recognised = set(roots).intersection(
        _GIT_ROOT_NAMES
        | _FOLD_ROOT_NAMES
        | _COORDINATE_ROOT_NAMES
        | _ATLAS_CURSOR_ROOT_NAMES
        | _ATLAS_HEAD_ROOT_NAMES
        | _BLUEPRINT_ROOT_NAMES
    )
    observations: dict[str, dict[str, Any]] = {}
    live_git_head: str | None = None
    if recognised.intersection(_GIT_ROOT_NAMES | _FOLD_ROOT_NAMES):
        live_git_head = _git_resolve_commit("HEAD")

    for name, declared in roots.items():
        if name in _GIT_ROOT_NAMES:
            resolved = _git_resolve_commit(declared)
            if resolved is None or live_git_head is None:
                state = "UNKNOWN"
            elif resolved == live_git_head:
                state = "CURRENT"
            elif _git_is_ancestor(resolved, live_git_head):
                state = "STALE-ANCESTOR"
            else:
                state = "DIVERGED"
            observations[name] = {
                "kind": "git-head",
                "declared": declared,
                "resolved": resolved,
                "live": live_git_head,
                "state": state,
            }
        elif name in _FOLD_ROOT_NAMES:
            folded = subprocess.run(
                [
                    "git",
                    "log",
                    "-1",
                    "--format=%H",
                    "--",
                    ".meaning_tree.json",
                    ".self_graded.json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            resolved = _git_resolve_commit(declared)
            state = (
                "CURRENT"
                if resolved and resolved == folded
                else ("STALE-OR-DIVERGED" if resolved else "UNKNOWN")
            )
            observations[name] = {
                "kind": "semantic-fold-head",
                "declared": declared,
                "resolved": resolved,
                "live": folded or None,
                "state": state,
            }
        elif name in _COORDINATE_ROOT_NAMES:
            try:
                from laplace.representation.recovery_coordinate import DEFAULT_COORDINATE, canonical_payload_digest

                document = json.loads(DEFAULT_COORDINATE.read_text(encoding="utf-8"))
                live = canonical_payload_digest(document)
                if declared == live:
                    state = "CURRENT"
                elif declared in _known_coordinate_payload_digests():
                    state = "SUPERSEDED"
                else:
                    state = "UNKNOWN"
                error = None
            except Exception as exc:  # noqa: BLE001 - unknown is the honest message face
                live, state = None, "UNKNOWN"
                error = f"{type(exc).__name__}: {exc}"
            observations[name] = {
                "kind": "recovery-coordinate-payload",
                "declared": declared,
                "live": live,
                "state": state,
                "error": error,
            }
        elif name in _ATLAS_CURSOR_ROOT_NAMES:
            try:
                token = drift_token()
                live_cursor = int(token["cursor"])
                declared_cursor = int(declared)
                state = (
                    "CURRENT"
                    if declared_cursor == live_cursor
                    else ("STALE-ANCESTOR" if declared_cursor < live_cursor else "AHEAD-UNKNOWN")
                )
                error = None
            except Exception as exc:  # noqa: BLE001
                live_cursor, state = None, "UNKNOWN"
                error = f"{type(exc).__name__}: {exc}"
            observations[name] = {
                "kind": "atlas-cursor",
                "declared": declared,
                "live": live_cursor,
                "state": state,
                "error": error,
            }
        elif name in _ATLAS_HEAD_ROOT_NAMES:
            try:
                token = drift_token()
                live = token.get("head_event_id")
                state = "CURRENT" if declared == live else "STALE-OR-DIVERGED"
                error = None
            except Exception as exc:  # noqa: BLE001
                live, state = None, "UNKNOWN"
                error = f"{type(exc).__name__}: {exc}"
            observations[name] = {
                "kind": "atlas-head-event",
                "declared": declared,
                "live": live,
                "state": state,
                "error": error,
            }
        elif name in _BLUEPRINT_ROOT_NAMES:
            observations[name] = {
                "kind": "blueprint-generation",
                "declared": declared,
                "live": None,
                "state": "UNMEASURED",
                "reason": (
                    "no O(1) generation token yet; per-message status refuses to hide a full "
                    "blueprint replay behind this observation"
                ),
            }
        elif name != "body":
            observations[name] = {
                "kind": "opaque",
                "declared": declared,
                "live": None,
                "state": "OPAQUE",
            }

    known_states = [
        observation["state"]
        for observation in observations.values()
        if observation["kind"] != "opaque"
    ]
    if any(state in {"STALE-OR-DIVERGED", "DIVERGED", "SUPERSEDED"} for state in known_states):
        state = "STALE"
    elif any(state in {"UNKNOWN", "AHEAD-UNKNOWN", "UNMEASURED"} for state in known_states):
        state = "PARTIAL"
    elif any(state == "STALE-ANCESTOR" for state in known_states):
        # The bound content remains reachable on the live fast-forward. Keep the exact root
        # state visible without turning normal concurrent building into a red alarm.
        state = "REACHABLE-ANCESTOR"
    elif known_states:
        state = "CURRENT"
    else:
        state = "OPAQUE"
    return {
        "schema_version": "laplace.fabric-dependency-freshness/1",
        "observed_at": _now(),
        "state": state,
        "known_root_count": len(known_states),
        "roots": observations,
    }


def _message_dependency_freshness(dependency_roots: Mapping[str, str]) -> dict[str, Any]:
    raw_send = dependency_roots.get(_DEPENDENCY_FRESHNESS_ROOT)
    if raw_send is None:
        send = {"state": "UNRECORDED", "reason": "message predates freshness stamping"}
    else:
        try:
            send = json.loads(str(raw_send))
        except json.JSONDecodeError as exc:
            send = {"state": "INVALID", "error": f"JSONDecodeError: {exc}"}
    return {
        "schema_version": "laplace.fabric-dependency-freshness-face/1",
        "send": send,
        "current": _dependency_freshness(dependency_roots),
    }


def _status_with_dependency_freshness(status: dict[str, Any]) -> dict[str, Any]:
    message = status.get("message") or {}
    roots = message.get("dependency_roots") or {}
    return {**status, "dependency_freshness": _message_dependency_freshness(roots)}


def _blueprint_manifest() -> tuple[Path, dict[str, Any]]:
    path = REPO_ROOT / "atlas" / "blueprint_manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "atlas.blueprint-manifest/1":
        raise StateTransitionRefused("blueprint manifest schema is unknown")
    return path, raw


def _git_attribute_values(
    paths: tuple[str, ...], attribute: str, *, source: str | None = None
) -> dict[str, str]:
    """Read one Git attribute for many paths without a process per hive chunk.

    Custody callers pass ``source="HEAD"`` so per-clone ``.git/info/attributes`` and an
    uncommitted/index-only ``.gitattributes`` cannot alter the transport verdict.
    """

    if not paths:
        return {}
    command = ["git", "check-attr", "-z", "--stdin"]
    if source is not None:
        command.append(f"--source={source}")
    command.append(attribute)
    run = subprocess.run(
        command,
        cwd=REPO_ROOT,
        input=("\0".join(paths) + "\0").encode("utf-8"),
        check=False,
        capture_output=True,
    )
    if run.returncode != 0:
        raise StoreError(
            "Git could not resolve blueprint authority transport attributes",
            attribute=attribute,
            error=run.stderr.decode("utf-8", errors="replace"),
        )
    fields = run.stdout.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) != 3 * len(paths):
        raise StoreError(
            "Git returned a malformed blueprint authority attribute set",
            attribute=attribute,
            expected=3 * len(paths),
            got=len(fields),
        )
    values: dict[str, str] = {}
    for offset in range(0, len(fields), 3):
        try:
            path = fields[offset].decode("utf-8", errors="strict")
            returned_attribute = fields[offset + 1].decode("ascii", errors="strict")
            value = fields[offset + 2].decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise StoreError("Git blueprint authority attribute output is malformed") from exc
        if returned_attribute != attribute or path in values:
            raise StoreError(
                "Git blueprint authority attribute output is contradictory",
                path=path,
                attribute=returned_attribute,
            )
        values[path] = value
    if set(values) != set(paths):
        raise StoreError(
            "Git returned an incomplete blueprint authority attribute set",
            attribute=attribute,
        )
    return values


def _verify_lfs_tree_pointer(*, path: str, tree_oid: str) -> None:
    """Prove that a committed LFS pointer names the exact working payload bytes.

    The HEAD tree intentionally carries a small pointer rather than the SQLite payload.  Reading
    that blob is non-mutating; unlike ``git hash-object`` with active filters, this verifier cannot
    recreate a missing object in ``.git/lfs/objects`` and thereby repair the defect it measures.
    """

    pointer_run = subprocess.run(
        ["git", "cat-file", "blob", tree_oid],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    if pointer_run.returncode != 0:
        raise StoreError(
            "Git could not read a committed blueprint LFS pointer",
            path=path,
            tree_oid=tree_oid,
            error=pointer_run.stderr.decode("utf-8", errors="replace"),
        )
    match = re.fullmatch(
        rb"version https://git-lfs\.github\.com/spec/v1\n"
        rb"oid sha256:([0-9a-f]{64})\n"
        rb"size ([0-9]+)\n",
        pointer_run.stdout,
    )
    if match is None:
        raise StoreError(
            "committed blueprint LFS pointer is not canonical",
            path=path,
            tree_oid=tree_oid,
        )
    target = REPO_ROOT / path
    digest = hashlib.sha256()
    size = 0
    try:
        with target.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise StoreError("blueprint LFS payload is unreadable", path=path) from exc
    expected_digest = match.group(1).decode("ascii")
    expected_size = int(match.group(2))
    if digest.hexdigest() != expected_digest or size != expected_size:
        raise StoreError(
            "blueprint LFS payload disagrees with its indexed pointer",
            path=path,
            expected_digest=f"sha256:{expected_digest}",
            actual_digest=f"sha256:{digest.hexdigest()}",
            expected_size=expected_size,
            actual_size=size,
        )


@lru_cache(maxsize=4)
def _blueprint_generation_projection(
    store_path: str,
    store_mtime_ns: int,
    store_size: int,
    manifest_digest: str,
) -> dict[str, Any]:
    """Replay a blueprint generation once per durable store version.

    Source-root freshness is intentionally checked outside this cache: changing governed bytes
    must refuse immediately even when the Atlas event database itself has not moved.
    """

    del store_mtime_ns, store_size, manifest_digest
    from atlas.blueprint import current_blueprint_generation

    store = ConceptricStore(
        Path(store_path), read_only=True, expected_store_role="blueprint-generation",
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    state = store.current_state()
    generation = current_blueprint_generation(store)
    completion_history = _blueprint_completion_history(store.events())
    if (
        not completion_history
        or completion_history[-1]["generation_id"] != generation.generation_id
    ):
        raise StoreError(
            "current blueprint generation is not the latest exact completion event",
            current_generation_id=generation.generation_id,
            latest_completion=(completion_history[-1] if completion_history else None),
        )
    clause_by_content = {
        str(clause["content_handle"]): dict(clause) for clause in generation.clauses
    }
    bindings_by_logical: dict[str, list[dict[str, Any]]] = {}
    finding_by_id = {str(finding["finding_id"]): dict(finding) for finding in generation.findings}
    for raw_binding in generation.bindings:
        binding = dict(raw_binding)
        implementation = REPO_ROOT / str(binding["implementation_path"])
        binding["implementation_size"] = (
            implementation.stat().st_size if implementation.is_file() else None
        )
        binding["required_findings"] = [
            {
                key: finding[key]
                for key in (
                    "finding_id",
                    "object_id",
                    "relation",
                    "evidence_state",
                    "source_path",
                    "start",
                    "end",
                    "proof_scope",
                )
                if key in finding
            }
            for finding_id in binding.get("required_finding_ids", ())
            if (finding := finding_by_id.get(str(finding_id))) is not None
        ]
        bindings_by_logical.setdefault(str(binding["clause_logical_id"]), []).append(binding)

    current_materializations: list[dict[str, Any]] = []
    stale_materializations = 0
    for materialization in reversed(tuple(state.materializations.values())):
        if dict(materialization.dependency_frontier) != dict(generation.source_roots):
            stale_materializations += 1
            continue
        results = []
        for content_handle in materialization.result_handles:
            clause = clause_by_content.get(str(content_handle))
            if clause is None:
                continue
            results.append(
                {
                    "logical_id": clause["logical_id"],
                    "subject_id": clause["subject_id"],
                    "subject_handle": clause["subject_handle"],
                    "version_edge_id": clause["version_edge_id"],
                    "object_id": clause["object_id"],
                    "content_handle": clause["content_handle"],
                    "exact_byte_hash": clause["exact_byte_hash"],
                    "source_path": clause["source_path"],
                    "source_hash": clause["source_hash"],
                    "start": clause["start"],
                    "end": clause["end"],
                    "trail": list(clause["trail"]),
                    "design_role": clause["design_role"],
                    "fibre": clause["fibre"],
                    "implements": bindings_by_logical.get(str(clause["logical_id"]), []),
                }
            )
        current_materializations.append(
            {
                "materialization_id": materialization.materialization_id,
                "goal": materialization.goal,
                "fibre": materialization.fibre,
                "coverage": materialization.coverage,
                "dependency_frontier": dict(materialization.dependency_frontier),
                "results": results,
            }
        )
    return {
        "schema_version": "laplace.atlas-blueprint-projection/2",
        "generation_id": generation.generation_id,
        "generation_completion_history": completion_history,
        "pour_handle": generation.pour_handle,
        "pour_observation_event_id": generation.pour_observation_event_id,
        "encoder_id": generation.encoder_id,
        "embedding_batch_policy": generation.embedding_batch_policy,
        "assumption": generation.assumption,
        "entry_role": generation.entry_role,
        "role_fibres": dict(generation.role_fibres),
        "source_roots": dict(generation.source_roots),
        "counts": {
            "clauses": len(generation.clauses),
            "clusters": len(generation.clusters),
            "implementation_bindings": len(generation.bindings),
            "evidence_findings": len(generation.findings),
            "current_materializations": len(current_materializations),
            "stale_materializations": stale_materializations,
        },
        "current_materializations": current_materializations,
    }


def _blueprint_completion_history(events: tuple[AtlasEvent, ...]) -> list[dict[str, Any]]:
    """Expose exact temporal evidence without pretending it is revision topology.

    Old blueprint schemas predate ``BlueprintGeneration.from_dict`` support, but their Atlas
    events remain content-addressed and hash-verified.  Retaining their completion identity is
    enough for the recovery-coordinate scaffold to prove that a recorded generation occurred in
    this exact append-only history.  Ledger order is deliberately named, not silently promoted to
    semantic supersession; ``CR-blueprint-generation-append-order-currentness`` owns its removal.
    """

    history: list[dict[str, Any]] = []
    for ledger_position, event in enumerate(events, start=1):
        schema = event.payload.get("schema_version")
        if (
            event.kind != EventKind.OBSERVATION
            or not isinstance(schema, str)
            or not schema.startswith("atlas.blueprint-generation/")
        ):
            continue
        generation_id = str(event.payload.get("generation_id") or "")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", generation_id) is None:
            raise StoreError(
                "blueprint completion carries a malformed generation id",
                completion_event_id=event.event_id,
                generation_id=generation_id,
            )
        history.append(
            {
                "generation_id": generation_id,
                "completion_event_id": event.event_id,
                "ledger_position": ledger_position,
                "generation_schema": schema,
            }
        )
    return history


def blueprint_projection(
    *, materialization_limit: int | None = 3, result_limit: int | None = None
) -> dict[str, Any]:
    """Serve the current self-hosted blueprint with per-source frontier honesty.

    The projection carries stable subjects beside immutable content versions and resolves every
    stored current spectral route to exact spans plus implementation/evidence joins.  It never
    invokes an encoder: route creation remains an explicit, receipted Atlas act.
    """

    manifest_path, raw = _blueprint_manifest()
    blueprint_root = (REPO_ROOT / str(raw["store"])).resolve()
    database = blueprint_root / "conceptric.sqlite3"
    stat = database.stat()
    full = _blueprint_generation_projection(
        str(blueprint_root),
        stat.st_mtime_ns,
        stat.st_size,
        hash_bytes(manifest_path.read_bytes()),
    )
    moved = []
    for relative, expected in full["source_roots"].items():
        target = REPO_ROOT / relative
        actual = hash_bytes(target.read_bytes()) if target.is_file() else None
        if actual != expected:
            moved.append({"path": relative, "expected": expected, "actual": actual})
    limit = (
        len(full["current_materializations"])
        if materialization_limit is None
        else max(0, min(int(materialization_limit), 12))
    )
    result_cap = None if result_limit is None else max(1, min(int(result_limit), 24))
    materializations = []
    for source in full["current_materializations"][:limit]:
        results = source["results"] if result_cap is None else source["results"][:result_cap]
        materializations.append(
            {
                **{key: value for key, value in source.items() if key != "results"},
                "results": results,
                "omitted_results": max(0, len(source["results"]) - len(results)),
            }
        )
    return {
        **{key: value for key, value in full.items() if key != "current_materializations"},
        "current": not moved,
        "moved_source_roots": moved,
        "current_materializations": materializations,
        "omitted_materializations": max(
            0, len(full["current_materializations"]) - len(materializations)
        ),
        "read_only": True,
    }


def blueprint_custody_projection() -> dict[str, Any]:
    """Verify the blueprint's exact authority set is replayable and travels through Git.

    Schema v1 is reported honestly as the still-unmigrated monolith.  Once the store becomes
    hived, the current custody seal, historical migration prefix, zero-orphan reachability and
    checkpointed WAL are mandatory.  In both cases every authoritative path must exist with exact
    bytes in the committed HEAD tree.  The index is deliberately irrelevant: a staged file does
    not travel in a clone of HEAD, and a custody read must never run a clean filter that can
    repopulate missing LFS storage while measuring it.
    """

    _manifest_path, raw = _blueprint_manifest()
    root = (REPO_ROOT / str(raw["store"])).resolve()
    try:
        root.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise StoreError(
            "blueprint authority is outside repository custody", path=str(root)
        ) from exc
    store = ConceptricStore(
        root, read_only=True, expected_store_role="blueprint-generation",
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    store._refuse_uncheckpointed_authority()
    required = [store.path]
    if store.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA:
        state = store.current_state()
        custody = {
            "status": "legacy-monolith",
            "event_count": state.event_count,
            "head_event_id": state.head_event_id,
            "migration_claim": "none; hived migration remains frozen",
        }
    else:
        seal = store.verify_custody()
        with store._connect() as connection:
            handles = tuple(
                str(row["event_handle"])
                for row in connection.execute("SELECT event_handle FROM events ORDER BY sequence")
            )
        required.extend(store.hive.key_path(handle) for handle in handles)
        required.append(store.custody_receipt_path)
        if store.migration_receipt_path.is_file():
            required.append(store.migration_receipt_path)
        custody = {
            "status": "sealed-hived-authority",
            "event_count": seal["event_count"],
            "head_digest": seal["head_digest"],
            "authority_paths_root": seal["authority_paths_root"],
            "migration": seal["migration"],
        }

    relative_paths: list[str] = []
    for path in required:
        try:
            relative_paths.append(path.resolve().relative_to(REPO_ROOT.resolve()).as_posix())
        except ValueError as exc:
            raise StoreError(
                "blueprint hive path is outside repository custody", path=str(path)
            ) from exc
    root_relative = root.relative_to(REPO_ROOT.resolve()).as_posix()
    tree_run = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD", "--", root_relative],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    if tree_run.returncode != 0:
        raise StoreError(
            "Git could not enumerate committed blueprint custody",
            error=tree_run.stderr.decode("utf-8", errors="replace"),
        )
    tree_entries: dict[str, str] = {}
    for item in tree_run.stdout.split(b"\0"):
        if not item:
            continue
        try:
            header, raw_path = item.split(b"\t", 1)
            _mode, raw_kind, raw_oid = header.split(b" ", 2)
            path = raw_path.decode("utf-8", errors="strict")
            kind = raw_kind.decode("ascii", errors="strict")
            oid = raw_oid.decode("ascii", errors="strict")
        except (UnicodeError, ValueError) as exc:
            raise StoreError("Git HEAD entry for blueprint custody is malformed") from exc
        if kind != "blob" or path in tree_entries:
            raise StoreError(
                "blueprint custody HEAD contains a non-blob or duplicate path",
                path=path,
                kind=kind,
            )
        tree_entries[path] = oid
    tracked = set(tree_entries)
    missing = tuple(sorted(set(relative_paths) - tracked))
    if missing:
        raise StoreError(
            "blueprint authority is present but does not travel in the Git HEAD tree",
            missing_count=len(missing),
            missing=missing[:12],
            omitted=max(0, len(missing) - 12),
        )
    required_paths = tuple(sorted(set(relative_paths)))
    if any("\n" in path or "\r" in path for path in required_paths):
        raise StoreError("blueprint authority path cannot be hashed through Git safely")
    # Resolve attributes from HEAD itself.  The working tree and .git/info/attributes are not
    # allowed to define how a different machine will interpret the committed bytes.
    filter_by_path = _git_attribute_values(required_paths, "filter", source="HEAD")
    unsupported_filters = tuple(
        sorted(
            path
            for path, value in filter_by_path.items()
            if value not in {"unspecified", "unset", "lfs"}
        )
    )
    if unsupported_filters:
        raise StoreError(
            "blueprint authority uses an unsupported Git content filter",
            paths=unsupported_filters[:12],
            omitted=max(0, len(unsupported_filters) - 12),
        )
    direct_paths = tuple(path for path in required_paths if filter_by_path[path] != "lfs")
    working_oids: dict[str, str] = {}
    if direct_paths:
        hash_run = subprocess.run(
            ["git", "hash-object", "--no-filters", "--stdin-paths"],
            cwd=REPO_ROOT,
            input=("\n".join(direct_paths) + "\n").encode("utf-8"),
            check=False,
            capture_output=True,
        )
        if hash_run.returncode != 0:
            raise StoreError(
                "Git could not hash raw working blueprint authority bytes",
                error=hash_run.stderr.decode("utf-8", errors="replace"),
            )
        hashes = tuple(
            line.decode("ascii", errors="strict") for line in hash_run.stdout.splitlines() if line
        )
        if len(hashes) != len(direct_paths):
            raise StoreError(
                "Git returned an incomplete raw blueprint authority hash set",
                expected=len(direct_paths),
                got=len(hashes),
            )
        working_oids.update(zip(direct_paths, hashes, strict=True))
    mismatched = tuple(path for path in direct_paths if tree_entries[path] != working_oids[path])
    if mismatched:
        raise StoreError(
            "blueprint authority working payload disagrees with the Git HEAD tree",
            mismatched_count=len(mismatched),
            mismatched=mismatched[:12],
            omitted=max(0, len(mismatched) - 12),
        )
    for path in required_paths:
        if filter_by_path[path] == "lfs":
            _verify_lfs_tree_pointer(path=path, tree_oid=tree_entries[path])

    hive_relative = store.hive_root.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    hive_prefix = hive_relative.rstrip("/") + "/"
    tracked_hives = {path for path in tracked if path.startswith(hive_prefix)}
    required_hives = {path for path in required_paths if path.startswith(hive_prefix)}
    tree_only_hives = tuple(sorted(tracked_hives - required_hives))
    if tree_only_hives:
        raise StoreError(
            "Git HEAD tree carries blueprint hive chunks outside the causal authority set",
            orphan_count=len(tree_only_hives),
            orphans=tree_only_hives[:12],
            omitted=max(0, len(tree_only_hives) - 12),
        )
    projection_relative = (
        store.projection_path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    )
    return {
        "schema_version": "laplace.atlas-blueprint-custody-projection/1",
        **custody,
        "store_root": root.relative_to(REPO_ROOT.resolve()).as_posix(),
        "authoritative_path_count": len(relative_paths),
        "all_authority_tracked": True,
        "authority_git_ref": "HEAD",
        "all_authority_head_representations_exact": True,
        "all_authority_payloads_exact": True,
        "all_authority_head_bytes_exact": True,
        "authority_transport_counts": {
            "direct": sum(value != "lfs" for value in filter_by_path.values()),
            "git-lfs": sum(value == "lfs" for value in filter_by_path.values()),
        },
        "head_only_orphan_hives": 0,
        "disposable_projection_tracked": projection_relative in tracked,
        "read_only": True,
    }


def _resolve_blueprint_clause(
    generation: Any,
    reference: str,
    *,
    object_reader: Callable[[str], Mapping[str, Any]],
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Resolve a completed clause through its verified banked object, never newer source."""

    identity_fields = (
        "logical_id",
        "subject_id",
        "subject_handle",
        "object_id",
        "content_handle",
    )
    matches = [
        dict(clause)
        for clause in generation.clauses
        if any(str(clause.get(field, "")) == reference for field in identity_fields)
    ]
    if len(matches) != 1:
        raise StateTransitionRefused(
            "blueprint reference must resolve exactly one current clause",
            reference=reference,
            matches=len(matches),
        )
    clause = matches[0]
    item = object_reader(str(clause["object_id"]))
    attributes = item.get("attributes", {})
    if (
        item.get("object_id") != clause["object_id"]
        or item.get("kind") != "source-leaf"
        or item.get("content_handle") != clause["content_handle"]
        or attributes.get("logical_id") != clause["logical_id"]
        or attributes.get("subject_handle") != clause["subject_handle"]
        or attributes.get("exact_byte_hash") != clause["exact_byte_hash"]
    ):
        raise StateTransitionRefused(
            "banked blueprint object contradicts its completed clause",
            object_id=clause["object_id"],
        )
    text = attributes.get("text")
    if not isinstance(text, str):
        raise StateTransitionRefused(
            "blueprint clause has no banked text",
            object_id=clause["object_id"],
        )
    exact = text.encode("utf-8")
    start, end = int(clause["start"]), int(clause["end"])
    if start < 0 or end - start != len(exact) or hash_bytes(exact) != clause["exact_byte_hash"]:
        raise StateTransitionRefused(
            "banked blueprint clause does not match its exact byte span",
            path=str(clause["source_path"]),
            start=start,
            end=end,
        )
    bindings = [
        dict(binding)
        for binding in generation.bindings
        if str(binding.get("clause_logical_id", "")) == str(clause["logical_id"])
    ]
    for binding in bindings:
        implementation = repo_root / str(binding["implementation_path"])
        try:
            actual = hash_bytes(implementation.read_bytes())
        except OSError:
            actual = None
        binding["current_implementation_hash"] = actual
        binding["implementation_current"] = actual == binding.get("implementation_hash")
    return {
        "clause": clause,
        "text": text,
        "implements": bindings,
        "content_basis": "completed-generation-banked-bytes",
    }


def blueprint_descent(*, reference: str) -> dict[str, Any]:
    """Resolve exact banked clause bytes and report working-source currency separately.

    This never runs an encoder or chooses a semantic neighbour.  The caller must supply one of the
    stable identities already returned by spectral routing.
    """

    manifest_path, raw = _blueprint_manifest()
    blueprint_root = (REPO_ROOT / str(raw["store"])).resolve()
    from atlas.blueprint import blueprint_source_currency, current_blueprint_generation

    head = ConceptricStore.read_drift_token(blueprint_root)
    store = ConceptricStore(
        blueprint_root, read_only=True, expected_store_role="blueprint-generation",
        extra_authority_files=EXTRA_AUTHORITY_FILES,
    )
    generation = current_blueprint_generation(store)
    read_metrics: dict[str, Any] = {"generation_selection": "verified-event-history-scan"}

    def read_object(object_id: str) -> Mapping[str, Any]:
        if store.projection_path.is_file():
            result = ConceptricStore.read_atlas_object(blueprint_root, reference=object_id)
            read_metrics.update(result["read_metrics"])
            return result["value"]
        # Cold copies may omit the disposable index. Fold verified authority in memory;
        # do not create an index, adopt a writer, or bypass a present but damaged index.
        state = store.current_state()
        read_metrics.update(object_resolution="verified-authority-fold", global_history_replayed=True)
        item = state.graph_objects.get(object_id)
        if item is None:
            raise StateTransitionRefused("banked blueprint object is absent", object_id=object_id)
        return item.to_dict()

    resolved = _resolve_blueprint_clause(
        generation, reference, object_reader=read_object, repo_root=REPO_ROOT,
    )
    if ConceptricStore.read_drift_token(blueprint_root) != head:
        raise HistoryChainMismatch("blueprint moved during exact descent", code="MOVED")
    currency = blueprint_source_currency(
        REPO_ROOT, generation, container_root=REPO_ROOT / "atlas",
        dataset_roots={name: (manifest_path.parent / root).resolve()
                       for name, root in raw.get("dataset_roots", {}).items()},
    )
    moved = currency["moved"]
    return {
        "schema_version": "laplace.atlas-blueprint-descent/1",
        "generation_id": generation.generation_id,
        "pour_handle": generation.pour_handle,
        **resolved,
        "manifest_hash": hash_bytes(manifest_path.read_bytes()),
        "generation_current": not moved,
        "generation_selection": "latest-completed",
        "source_currency": currency["source_roots"],
        "moved_source_roots": moved,
        "read_head": head,
        "read_metrics": read_metrics,
        "read_only": True,
        "storage_access": "sqlite mode=ro/query_only; bounded shared flock; authority writes none",
        "routing_claim": "none; the reference was selected before this exact descent",
    }


def lifecycle(
    *,
    action: str,
    receipt_id: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Bank one explicit wake/cold-wake/sew-up/sleep transition."""

    store = _store()
    state = store.current_state()
    act = LifecycleAction(action)
    endpoints = {
        LifecycleAction.WAKE: (LifecyclePhase.SLEEPING, LifecyclePhase.AWAKE),
        LifecycleAction.COLD_WAKE: (LifecyclePhase.SLEEPING, LifecyclePhase.AWAKE),
        LifecycleAction.SEW_UP: (LifecyclePhase.AWAKE, LifecyclePhase.SEWING_UP),
        LifecycleAction.SLEEP: (LifecyclePhase.SEWING_UP, LifecyclePhase.SLEEPING),
    }
    start, end = endpoints[act]
    if state.lifecycle != start:
        raise StateTransitionRefused(
            "lifecycle action does not start at the durable phase",
            expected=start.value,
            got=state.lifecycle.value,
        )
    correlation = _correlation(
        correlation_id,
        {"action": action, "receipt_id": receipt_id, "head": state.head_event_id},
    )
    event = _event(
        EventKind.LIFECYCLE,
        LifecycleTransition(act, start, end, receipt_id).to_dict(),
        actor=SeatRole.SYSTEM,
        subject=f"lifecycle:{receipt_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        note=f"provider lifecycle {action}",
    )
    stored = store.append(event)
    return {"schema_version": BRIDGE_SCHEMA, "receipt": _receipt(stored), "phase": end.value}


def seat_transition(
    *,
    seat_id: str,
    role: str,
    action: str,
    charter_ref: str,
    holder_ref: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Found, relay, activate or close a logical seat without changing its identity."""

    store = _store()
    state = store.current_state()
    seat_action = SeatAction(action)
    current = state.seats.get(seat_id)
    if (
        seat_action == SeatAction.FOUND
        and current is not None
        and current.status == SeatStatus.ACTIVE
        and current.role == role
        and current.charter_ref == charter_ref
        and current.holder_ref == holder_ref
    ):
        return {
            "schema_version": BRIDGE_SCHEMA,
            "idempotent": True,
            "seat": current.to_dict(),
        }
    from_status = None if current is None else current.status
    to_status = {
        SeatAction.FOUND: SeatStatus.ACTIVE,
        SeatAction.RELAY: SeatStatus.RELAYING,
        SeatAction.ACTIVATE: SeatStatus.ACTIVE,
        SeatAction.CLOSE: SeatStatus.CLOSED,
    }[seat_action]
    transition = SeatTransition(
        seat_id,
        SeatRole(role),
        seat_action,
        from_status,
        to_status,
        charter_ref,
        holder_ref,
    )
    correlation = _correlation(
        correlation_id,
        {"seat_id": seat_id, "action": action, "holder_ref": holder_ref},
    )
    event = _event(
        EventKind.SEAT,
        transition.to_dict(),
        actor=SeatRole.SYSTEM,
        subject=f"seat:{seat_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        note=f"logical seat {seat_id} {action}",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "receipt": _receipt(stored),
        "seat": store.provider_snapshot()["seats"][seat_id],
    }


def _live_provider_identity_attestation(seat_id: str) -> dict[str, Any]:
    """Use the startup gate's one live provider-identity reader.

    Keeping the check behind one function avoids an independently drifting bridge
    copy of watcher identity semantics while still making it easy to isolate in
    focused bridge tests.
    """

    from laplace.engine.startup_mail_gate import provider_identity_proof

    return provider_identity_proof(seat_id)


def _provider_identity_from_proof(
    *,
    store: ConceptricStore,
    proof_handle: str,
) -> Mapping[str, Any]:
    try:
        proof = json.loads(BlobStore(store.root / "blobs").get(proof_handle).decode("utf-8"))
    except (BlobMissing, BlobHashMismatch, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateTransitionRefused("bound occupancy identity proof is unavailable") from exc
    identity = proof.get("provider_identity")
    return identity if isinstance(identity, Mapping) else {}


def _provider_identity_pair_is_verified(
    *,
    proved: Mapping[str, Any],
    live: Mapping[str, Any],
    seat_id: str,
    holder_ref: str,
) -> bool:
    generation = proved.get("watcher_lease_generation")
    live_generation = live.get("watcher_lease_generation")
    target = proved.get("watcher_target_thread_id")
    live_target = live.get("watcher_target_thread_id")
    _provider_name, separator, provider_task_id = holder_ref.partition(":")
    return (
        proved.get("state") == "VERIFIED"
        and live.get("state") == "VERIFIED"
        and proved.get("provider_session_ref") == holder_ref
        and live.get("provider_session_ref") == holder_ref
        and proved.get("watcher_seat_id") == seat_id
        and live.get("watcher_seat_id") == seat_id
        and proved.get("identity_kind") == live.get("identity_kind")
        and proved.get("provider") == live.get("provider")
        and isinstance(generation, str)
        and bool(generation.strip())
        and generation == live_generation
        and isinstance(target, str)
        and bool(target.strip())
        and target == live_target
        and bool(separator)
        and target == provider_task_id
    )


def _authenticated_provider_identity(
    *,
    store: ConceptricStore,
    seat_id: str,
    occupancy: Any,
    authority_cursor: int,
    authority_head_event_id: str | None,
) -> dict[str, str]:
    """Prove this process is the current holder of one routing-authoritative seat."""

    if occupancy is None or not occupancy.routing_authority or occupancy.binding is None:
        raise StateTransitionRefused(
            "caller authentication requires bound routing-authoritative occupancy"
        )
    live = dict(_live_provider_identity_attestation(seat_id))
    joined_identity = _provider_identity_from_proof(
        store=store,
        proof_handle=occupancy.join.information_proof_handle,
    )
    generation = live.get("watcher_lease_generation")
    binding_exact = (
        occupancy.binding.provider_session_ref == occupancy.join.holder_ref
        and occupancy.binding.function == occupancy.join.function
        and occupancy.binding.provider_identity_proof_handle
        == occupancy.join.information_proof_handle
    )
    verified = binding_exact and (
        _provider_identity_pair_is_verified(
            proved=joined_identity,
            live=live,
            seat_id=seat_id,
            holder_ref=occupancy.join.holder_ref,
        )
    )
    lease_fields = (
        "provider_session_ref",
        "provider",
        "identity_kind",
        "watcher_seat_id",
        "watcher_target_thread_id",
        "watcher_lease_generation",
    )
    _provider_name, separator, provider_task_id = occupancy.join.holder_ref.partition(":")
    target = joined_identity.get("watcher_target_thread_id")
    interval = live.get("watcher_interval_seconds")
    same_unhealthy_lease = (
        not verified
        and binding_exact
        and joined_identity.get("state") == "VERIFIED"
        and live.get("state") == "UNVERIFIED"
        and all(joined_identity.get(field) == live.get(field) for field in lease_fields)
        and joined_identity.get("provider_session_ref") == occupancy.join.holder_ref
        and joined_identity.get("watcher_seat_id") == seat_id
        and isinstance(generation, str)
        and bool(generation.strip())
        and isinstance(target, str)
        and bool(target.strip())
        and bool(separator)
        and target == provider_task_id
        and type(interval) in {int, float}
        and 0.5 <= float(interval) <= 10.0
    )
    if same_unhealthy_lease:
        time.sleep(float(interval) + 0.5)
        live = dict(_live_provider_identity_attestation(seat_id))
        generation = live.get("watcher_lease_generation")
        verified = binding_exact and _provider_identity_pair_is_verified(
            proved=joined_identity,
            live=live,
            seat_id=seat_id,
            holder_ref=occupancy.join.holder_ref,
        )
        if verified:
            current_tip = drift_token()
            if (
                current_tip.get("cursor") != authority_cursor
                or current_tip.get("head_event_id") != authority_head_event_id
            ):
                raise StateTransitionRefused(
                    "Atlas authority moved during provider identity stabilization",
                    seat_id=seat_id,
                    expected_cursor=authority_cursor,
                    expected_head_event_id=authority_head_event_id,
                    observed_tip=current_tip,
                )
    if not verified:
        raise StateTransitionRefused(
            "live provider identity does not authenticate the current seat holder",
            seat_id=seat_id,
            expected_holder=occupancy.join.holder_ref,
            observed_holder=live.get("provider_session_ref"),
            expected_generation=joined_identity.get("watcher_lease_generation"),
            observed_generation=generation,
            observed_state=live.get("state"),
        )
    proof_handle = BlobStore(store.root / "blobs").put(
        (canonical_json(live) + "\n").encode("utf-8")
    )
    return {
        "provider_session_ref": occupancy.join.holder_ref,
        "provider_identity_proof_handle": proof_handle,
        "provider_identity_generation": str(generation),
    }


def seat_join(
    *,
    seat_id: str,
    holder_ref: str,
    function: str,
    information_proof: Mapping[str, Any],
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Bank a proved join and, when independently attested, bind its occupant.

    The local gate record is placed in Atlas custody and cited by the event.  A
    Joining never rewrites the logical seat registry.  The registered holder is a
    logical principal; ``holder_ref`` is the ephemeral provider task.  Only a
    watcher-backed provider identity can bridge those two types and grant routing
    authority.
    """

    store = _store()
    state = store.current_state()
    registered = state.seats.get(seat_id)
    if registered is None or registered.status == SeatStatus.CLOSED:
        raise StateTransitionRefused("only a registered live chair can be joined")
    claimed_function = SeatRole(function)
    if information_proof.get("state") != "MAIL_READY":
        raise StateTransitionRefused("seat join requires the terminal MAIL_READY gate record")
    if information_proof.get("seat_id") != seat_id:
        raise StateTransitionRefused("seat join gate record belongs to another logical chair")
    if not holder_ref.strip():
        raise StateTransitionRefused("seat join requires an exact provider-session holder")
    if state.active_assumption is None or state.active_fibre is None:
        raise StateTransitionRefused("seat join requires an active assumption fibre")

    provider_identity = information_proof.get("provider_identity")
    if not isinstance(provider_identity, Mapping):
        provider_identity = {}
    live_identity = dict(_live_provider_identity_attestation(seat_id))
    identity_attestation: dict[str, Any] = {
        "schema_version": "laplace.provider-identity-stabilization/1",
        "stabilization_attempted": False,
        "wait_seconds": 0.0,
        "observations": [live_identity],
    }
    identity_verified = _provider_identity_pair_is_verified(
        proved=provider_identity,
        live=live_identity,
        seat_id=seat_id,
        holder_ref=holder_ref,
    )
    lease_fields = (
        "provider_session_ref",
        "provider",
        "identity_kind",
        "watcher_seat_id",
        "watcher_target_thread_id",
        "watcher_lease_generation",
    )
    _provider_name, separator, provider_task_id = holder_ref.partition(":")
    target = provider_identity.get("watcher_target_thread_id")
    generation = provider_identity.get("watcher_lease_generation")
    interval = live_identity.get("watcher_interval_seconds")
    same_unhealthy_lease = (
        not identity_verified
        and provider_identity.get("state") == "VERIFIED"
        and live_identity.get("state") == "UNVERIFIED"
        and all(provider_identity.get(field) == live_identity.get(field) for field in lease_fields)
        and provider_identity.get("provider_session_ref") == holder_ref
        and provider_identity.get("watcher_seat_id") == seat_id
        and isinstance(generation, str)
        and bool(generation.strip())
        and isinstance(target, str)
        and bool(target.strip())
        and bool(separator)
        and target == provider_task_id
        and type(interval) in {int, float}
        and 0.5 <= float(interval) <= 10.0
    )
    if same_unhealthy_lease:
        wait_seconds = float(interval) + 0.5
        identity_attestation.update(stabilization_attempted=True, wait_seconds=wait_seconds)
        time.sleep(wait_seconds)
        live_identity = dict(_live_provider_identity_attestation(seat_id))
        identity_attestation["observations"].append(live_identity)
        identity_verified = _provider_identity_pair_is_verified(
            proved=provider_identity,
            live=live_identity,
            seat_id=seat_id,
            holder_ref=holder_ref,
        )
    if identity_attestation["stabilization_attempted"] and identity_verified:
        current_tip = drift_token()
        identity_attestation["authority_tip_after_stabilization"] = current_tip
        if (
            current_tip.get("cursor") != state.event_count
            or current_tip.get("head_event_id") != state.head_event_id
        ):
            raise StateTransitionRefused(
                "Atlas authority moved during provider identity stabilization",
                seat_id=seat_id,
                holder_ref=holder_ref,
                state_cursor=state.event_count,
                state_head_event_id=state.head_event_id,
                identity_attestation=identity_attestation,
            )

    current = state.seat_occupancies.get(seat_id)
    renewal_predecessor_binding_event_id = None
    retired_provider_identity_generation = None
    provider_identity_generation = provider_identity.get("watcher_lease_generation")
    holder_replaced = False
    if current is not None and current.routing_authority:
        if current.join.function != claimed_function:
            raise StateTransitionRefused(
                "current seat handover cannot change function",
                expected=current.join.function.value,
                got=claimed_function.value,
            )
        if not identity_verified:
            raise StateTransitionRefused(
                "current seat handover requires the live VERIFIED current watcher identity of the successor",
                seat_id=seat_id,
                current_holder=current.join.holder_ref,
                proposed_holder=holder_ref,
                observed_state=live_identity.get("state"),
                observed_generation=live_identity.get("watcher_lease_generation"),
                identity_attestation=identity_attestation,
            )
        current_identity = _provider_identity_from_proof(
            store=store,
            proof_handle=current.join.information_proof_handle,
        )
        current_generation = (
            None if current.binding is None else current.binding.provider_identity_generation
        ) or current_identity.get("watcher_lease_generation")
        current_target = current_identity.get("watcher_target_thread_id")
        _current_provider, current_separator, current_task_id = current.join.holder_ref.partition(
            ":"
        )
        current_identity_complete = (
            current_identity.get("state") == "VERIFIED"
            and current_identity.get("provider_session_ref") == current.join.holder_ref
            and current_identity.get("watcher_seat_id") == seat_id
            and isinstance(current_generation, str)
            and bool(current_generation.strip())
            and isinstance(current_target, str)
            and bool(current_target.strip())
            and bool(current_separator)
            and current_target == current_task_id
        )
        if not current_identity_complete:
            raise StateTransitionRefused(
                "current seat handover cannot resolve one exact predecessor generation"
            )
        if current_generation == provider_identity_generation:
            if current.join.holder_ref == holder_ref:
                return {
                    "schema_version": BRIDGE_SCHEMA,
                    "idempotent": True,
                    "renewed": False,
                    "provider_identity_generation": current_generation,
                    "information_proof_handle": current.join.information_proof_handle,
                    "occupancy": current.to_dict(),
                }
            raise StateTransitionRefused(
                "provider holder handover must advance the watcher generation",
                current_holder=current.join.holder_ref,
                proposed_holder=holder_ref,
                provider_identity_generation=provider_identity_generation,
            )
        retired_generation_bindings = {
            binding_event_id: state.retired_seat_binding_generations.get(binding_event_id)
            for binding_event_id in current.retired_binding_event_ids
        }
        matching_retired_bindings = sorted(
            binding_event_id
            for binding_event_id, generation in retired_generation_bindings.items()
            if generation == provider_identity_generation
        )
        if matching_retired_bindings:
            raise StateTransitionRefused(
                "seat handover refuses a retired watcher identity generation",
                seat_id=seat_id,
                holder_ref=holder_ref,
                provider_identity_generation=provider_identity_generation,
                retired_binding_event_ids=matching_retired_bindings,
            )
        renewal_predecessor_binding_event_id = current.binding_event_id
        assert renewal_predecessor_binding_event_id is not None
        retired_provider_identity_generation = str(current_generation)
        holder_replaced = current.join.holder_ref != holder_ref
    elif (
        current is not None
        and current.join.holder_ref == holder_ref
        and current.join.function == claimed_function
        and not identity_verified
    ):
        return {
            "schema_version": BRIDGE_SCHEMA,
            "idempotent": True,
            "renewed": False,
            "information_proof_handle": current.join.information_proof_handle,
            "occupancy": current.to_dict(),
        }

    information_proof_record = dict(information_proof)
    information_proof_record["seat_join_identity_attestation"] = identity_attestation
    proof_bytes = (canonical_json(information_proof_record) + "\n").encode("utf-8")
    proof_handle = _blobs().put(proof_bytes)
    delivered_rows = tuple(
        row for row in information_proof.get("delivered", ()) if isinstance(row, Mapping)
    )
    delivered_message_ids = tuple(
        dict.fromkeys(
            str(row["message_id"]) for row in delivered_rows if str(row.get("message_id") or "")
        )
    )
    reconstruction_event_ids = tuple(
        dict.fromkeys(
            str(row["reconstruction_event_id"])
            for row in delivered_rows
            if str(row.get("reconstruction_event_id") or "")
        )
    )
    unknown_reconstructions = sorted(set(reconstruction_event_ids) - set(state.event_ids))
    if unknown_reconstructions:
        raise StateTransitionRefused(
            "seat join cites reconstruction events outside Atlas",
            reconstruction_event_ids=unknown_reconstructions,
        )

    defects: list[str] = []
    if claimed_function.value != registered.role:
        defects.append(
            f"FUNCTION_MISMATCH:registered={registered.role}:claimed={claimed_function.value}"
        )
    if not identity_verified:
        defects.append(
            "PROVIDER_IDENTITY_UNVERIFIED:joined provider session has observational status"
        )
    joined = SeatJoinReceipt(
        seat_id=seat_id,
        holder_ref=holder_ref,
        function=claimed_function,
        registered_role=SeatRole(registered.role),
        registered_holder_ref=registered.holder_ref,
        mail_state="MAIL_READY",
        information_proof_handle=proof_handle,
        information_cursor=state.event_count,
        delivered_message_ids=delivered_message_ids,
        reconstruction_event_ids=reconstruction_event_ids,
        defects=tuple(defects),
        provider_identity_generation=(
            str(provider_identity_generation) if identity_verified else None
        ),
    )
    causes = tuple(
        dict.fromkeys(
            event_id
            for event_id in (
                state.head_event_id,
                *reconstruction_event_ids,
                renewal_predecessor_binding_event_id,
            )
            if event_id is not None
        )
    )
    correlation = _correlation(
        correlation_id,
        {
            "seat_id": seat_id,
            "holder_ref": holder_ref,
            "function": claimed_function.value,
            "information_proof_handle": proof_handle,
        },
    )
    event = _event(
        EventKind.SEAT_JOIN,
        joined.to_dict(),
        actor=claimed_function,
        subject=f"seat:{seat_id}:occupancy",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=causes,
        body_handle=proof_handle,
        note="startup mail information proof observed; routing authority unchanged",
    )
    binding_event = None
    if identity_verified and claimed_function.value == registered.role:
        registration_event_id = state.seat_registration_event_ids.get(seat_id)
        if registration_event_id is None:
            raise StateTransitionRefused(
                "seat occupancy binding cannot resolve the logical registration event"
            )
        binding = SeatOccupancyBinding(
            registered_seat_event_id=registration_event_id,
            join_event_id=event.event_id,
            registered_principal_ref=registered.holder_ref,
            provider_session_ref=holder_ref,
            provider_identity_proof_handle=proof_handle,
            seat_id=seat_id,
            function=claimed_function,
            provider_identity_generation=str(provider_identity_generation),
            predecessor_binding_event_id=(renewal_predecessor_binding_event_id),
            retired_provider_identity_generation=(retired_provider_identity_generation),
        )
        binding_event = _event(
            EventKind.SEAT_OCCUPANCY_BINDING,
            binding.to_dict(),
            actor=claimed_function,
            subject=f"seat:{seat_id}:binding",
            provider=provider,
            model=model,
            correlation_id=_correlation(correlation_id, binding.to_dict()),
            assumption=state.active_assumption,
            fibre=state.active_fibre,
            causation_ids=tuple(
                event_id
                for event_id in (
                    registration_event_id,
                    event.event_id,
                    renewal_predecessor_binding_event_id,
                )
                if event_id is not None
            ),
            body_handle=proof_handle,
            note="logical chair bound to watcher-attested provider session",
        )

    # A verified provider identity is one lifecycle act, not two independently durable
    # observations.  In particular, a same-holder generation renewal must never expose the
    # successor join without also retiring its exact predecessor binding.  ``append_many``
    # validates the second event against the first and commits the whole causal packet in one
    # SQLite transaction; a crash or insert fault therefore leaves the predecessor authoritative.
    packet = (event,) if binding_event is None else (event, binding_event)
    stored_packet = store.append_many(packet)
    joined_stored = stored_packet[0]
    binding_stored = stored_packet[1] if binding_event is not None else None

    occupancy = store.provider_snapshot()["seat_occupancy"][seat_id]
    result = {
        "schema_version": BRIDGE_SCHEMA,
        "renewed": renewal_predecessor_binding_event_id is not None,
        "holder_replaced": holder_replaced,
        "predecessor_binding_event_id": renewal_predecessor_binding_event_id,
        "retired_provider_identity_generation": (retired_provider_identity_generation),
        "provider_identity_generation": (
            str(provider_identity_generation) if identity_verified else None
        ),
        "provider_identity_attestation": identity_attestation,
        "receipt": _receipt(joined_stored),
        "information_proof_handle": proof_handle,
        "occupancy": occupancy,
    }
    if binding_stored is not None:
        result["binding_receipt"] = _receipt(binding_stored)
    return result


def checkout_regions(
    *,
    seat_id: str,
    holder_ref: str,
    function: str,
    act_id: str,
    regions: tuple[str, ...],
    expires_at: str,
    declaration_kind: str,
    declaration_ref: str,
    bootstrap_crutch: Mapping[str, Any] | None,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Acquire exact time-bounded repository regions for the latest joined holder.

    A native checkout starts only over a clean scope.  The one bootstrap mode may name
    pre-existing dirt, but it must carry the crutch and retirement trigger in the checkout
    event itself.  In either mode the lease explains custody; it does not make dirty source
    clean and it cannot close without a matching Git-backed checkin.
    """

    store = _store()
    state = store.current_state()
    claimed_function = SeatRole(function)
    occupancy = state.seat_occupancies.get(seat_id)
    if occupancy is None:
        raise StateTransitionRefused("region checkout requires a proved seat join")
    if not occupancy.routing_authority:
        raise StateTransitionRefused(
            "region checkout requires an authoritative provider-session binding"
        )
    if occupancy.join.holder_ref != holder_ref:
        raise StateTransitionRefused(
            "region checkout holder disagrees with latest seat occupancy",
            expected=occupancy.join.holder_ref,
            got=holder_ref,
        )
    if occupancy.join.function != claimed_function:
        raise StateTransitionRefused(
            "region checkout function disagrees with latest seat occupancy",
            expected=occupancy.join.function.value,
            got=claimed_function.value,
        )
    scope = tuple(dict.fromkeys(region.strip() for region in regions if region.strip()))
    for region in scope:
        validate_authority_region(region)
    kind = LeaseDeclarationKind(declaration_kind)
    crutch = None if bootstrap_crutch is None else BootstrapCrutch.from_dict(dict(bootstrap_crutch))
    if crutch is not None:
        retirement = bootstrap_crutch_retirement(state, crutch)
        if retirement["state"] == "RETIRED":
            raise StateTransitionRefused(
                "bootstrap crutch retirement trigger is satisfied",
                retirement=retirement,
            )
    base_git_head = _git_head()
    dirty = _git_dirty_paths()
    dirty_in_scope = tuple(path for path in dirty if _path_in_regions(path, scope))
    if kind == LeaseDeclarationKind.NATIVE and dirty_in_scope:
        raise StateTransitionRefused(
            "native region checkout refuses pre-existing worktree dirt",
            dirty_paths=dirty_in_scope,
        )
    identity = {
        "act_id": act_id,
        "seat_id": seat_id,
        "holder_ref": holder_ref,
        "function": claimed_function.value,
        "regions": list(scope),
        "base_git_head": base_git_head,
        "expires_at": expires_at,
        "declaration_kind": kind.value,
        "declaration_ref": declaration_ref,
        "preexisting_dirty_paths": list(dirty_in_scope),
        "bootstrap_crutch": None if crutch is None else crutch.to_dict(),
    }
    lease_id = "region-lease:" + chash(identity).removeprefix("sha256:")
    prior = state.region_leases.get(lease_id)
    if prior is not None:
        observed_at = _now()
        effective_state = _project_region_lease(
            prior,
            observed_at,
            state=state,
        )["effective_state"]
        if effective_state != "ACTIVE":
            raise StateTransitionRefused(
                "idempotent checkout replay cannot revive expired, closed, or displaced authority",
                lease_id=lease_id,
                effective_state=effective_state,
            )
        return {
            "schema_version": BRIDGE_SCHEMA,
            "idempotent": True,
            "lease": _project_region_lease(prior, observed_at, state=state),
        }
    checkout = RegionCheckout(
        lease_id=lease_id,
        act_id=act_id,
        seat_id=seat_id,
        holder_ref=holder_ref,
        function=claimed_function,
        regions=scope,
        base_git_head=base_git_head,
        expires_at=expires_at,
        declaration_kind=kind,
        declaration_ref=declaration_ref,
        preexisting_dirty_paths=dirty_in_scope,
        bootstrap_crutch=crutch,
    )
    causes = tuple(
        dict.fromkeys(
            event_id
            for event_id in (
                state.head_event_id,
                occupancy.join_event_id,
                occupancy.binding_event_id,
            )
            if event_id is not None
        )
    )
    correlation = _correlation(correlation_id, checkout.to_dict())
    event = _event(
        EventKind.REGION_CHECKOUT,
        checkout.to_dict(),
        actor=claimed_function,
        subject=f"lease:{lease_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=causes,
        note="joined holder checked out exact repository regions",
    )
    stored = store.append(event)
    lease = store.current_state().region_leases[lease_id]
    return {
        "schema_version": BRIDGE_SCHEMA,
        "idempotent": False,
        "receipt": _receipt(stored),
        "lease": _project_region_lease(
            lease,
            _now(),
            state=store.current_state(),
        ),
    }


def checkin_regions(
    *,
    lease_id: str,
    seat_id: str,
    holder_ref: str,
    function: str,
    outcome: str,
    evidence: Mapping[str, str],
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Close one lease with exact Git and worktree evidence from its scoped holder."""

    store = _store()
    state = store.current_state()
    lease = state.region_leases.get(lease_id)
    if lease is None:
        raise StateTransitionRefused("region checkin cites an unknown lease")
    if lease.checkin is not None:
        return {
            "schema_version": BRIDGE_SCHEMA,
            "idempotent": True,
            "lease": lease.to_dict(),
        }
    checkout = lease.checkout
    claimed_function = SeatRole(function)
    if (
        checkout.seat_id != seat_id
        or checkout.holder_ref != holder_ref
        or checkout.function != claimed_function
    ):
        raise StateTransitionRefused("region checkin does not match its checkout authority")
    occupancy = state.seat_occupancies.get(seat_id)
    if not lease.matches_occupancy(occupancy):
        raise StateTransitionRefused(
            "region checkin holder/function is no longer the latest seat occupancy lineage"
        )
    claimed_outcome = LeaseCheckinOutcome(outcome)
    result_git_head = _git_head()
    if claimed_outcome in {
        LeaseCheckinOutcome.COMMITTED,
        LeaseCheckinOutcome.NOOP,
    } and not _git_is_ancestor(checkout.base_git_head, result_git_head):
        raise StateTransitionRefused(
            "successful region checkin requires result HEAD to descend from checkout HEAD",
            base_git_head=checkout.base_git_head,
            result_git_head=result_git_head,
        )
    all_dirty = _git_dirty_paths()
    dirty_in_scope = tuple(path for path in all_dirty if _path_in_regions(path, checkout.regions))
    all_changed = _git_changed_paths(checkout.base_git_head, result_git_head)
    attribution = _git_holder_attribution(
        base=checkout.base_git_head,
        result=result_git_head,
        lease_id=lease_id,
        holder_ref=holder_ref,
        regions=checkout.regions,
    )
    if attribution["unattributed_paths"]:
        raise StateTransitionRefused(
            "region checkin found in-scope Git changes not attributable to this holder",
            paths=attribution["unattributed_paths"],
            required_trailers=attribution["required_trailers"],
        )
    if attribution.get("attributed_paths_outside_scope", []):
        raise StateTransitionRefused(
            "holder-attributed commit escapes its leased scope",
            paths=attribution["attributed_paths_outside_scope"],
        )
    committed_in_scope = tuple(attribution["attributed_paths"])
    if claimed_outcome == LeaseCheckinOutcome.COMMITTED and not attribution["attributed_commits"]:
        raise StateTransitionRefused(
            "committed region checkin requires at least one holder-attributed commit",
            required_trailers=attribution["required_trailers"],
        )
    outside_concurrent = tuple(
        attribution.get(
            "concurrent_paths_outside_scope",
            [path for path in all_changed if not _path_in_regions(path, checkout.regions)],
        )
    )
    proof = {
        "schema_version": "laplace.region-checkin-evidence/1",
        "lease_id": lease_id,
        "base_git_head": checkout.base_git_head,
        "result_git_head": result_git_head,
        "committed_paths": list(committed_in_scope),
        "net_changed_paths": list(all_changed),
        "concurrent_paths_outside_scope": list(outside_concurrent),
        "dirty_paths": list(dirty_in_scope),
        "holder_attribution": attribution,
        "caller_evidence": dict(evidence),
    }
    proof_handle = _blobs().put((canonical_json(proof) + "\n").encode("utf-8"))
    named_evidence = {**dict(evidence), "git_worktree_proof": proof_handle}
    checkin = RegionCheckin(
        lease_id=lease_id,
        seat_id=seat_id,
        holder_ref=holder_ref,
        function=claimed_function,
        outcome=claimed_outcome,
        base_git_head=checkout.base_git_head,
        result_git_head=result_git_head,
        committed_paths=committed_in_scope,
        dirty_paths=dirty_in_scope,
        evidence=named_evidence,
    )
    correlation = _correlation(correlation_id, checkin.to_dict())
    event = _event(
        EventKind.REGION_CHECKIN,
        checkin.to_dict(),
        actor=claimed_function,
        subject=f"lease:{lease_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=tuple(
            dict.fromkeys(
                event_id
                for event_id in (
                    state.head_event_id,
                    lease.checkout_event_id,
                    occupancy.binding_event_id,
                )
                if event_id is not None
            )
        ),
        body_handle=proof_handle,
        note=f"region lease checked in with outcome {outcome}",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "idempotent": False,
        "receipt": _receipt(stored),
        "evidence_handle": proof_handle,
        "lease": store.current_state().region_leases[lease_id].to_dict(),
    }


def _publication_row(
    state: ConceptricState, *, lease_id: str, publication_id: str
) -> tuple[Any, Any]:
    lease = state.region_leases.get(lease_id)
    if lease is None:
        raise StateTransitionRefused(
            "publication saga is UNKNOWN because its lease is absent",
            state="UNKNOWN",
            lease_id=lease_id,
            publication_id=publication_id,
        )
    publication = lease.publication
    if publication is None or publication.prepared.publication_id != publication_id:
        raise StateTransitionRefused(
            "publication saga is UNKNOWN for this exact lease/key",
            state="UNKNOWN",
            lease_id=lease_id,
            publication_id=publication_id,
        )
    return lease, publication


def region_publication(
    *, lease_id: str, publication_id: str, as_of: str = ""
) -> dict[str, Any]:
    """Read one keyed saga and classify exact Git/authority recovery state."""

    observed_at = as_of or _now()
    try:
        keyed = atlas_object(reference=lease_id, observed_at=observed_at)
        lease = keyed["value"]
        publication = lease.get("publication") if isinstance(lease, Mapping) else None
        prepared = (
            publication.get("prepared") if isinstance(publication, Mapping) else None
        )
        if (
            not isinstance(prepared, Mapping)
            or prepared.get("publication_id") != publication_id
        ):
            raise StateTransitionRefused(
                "publication saga is UNKNOWN for this exact lease/key", state="UNKNOWN"
            )
    except AtlasError as exc:
        return {
            "schema_version": "laplace.region-publication-status/1",
            "state": getattr(exc, "detail", {}).get("state", "UNKNOWN"),
            "lease_id": lease_id,
            "publication_id": publication_id,
            "reason": str(exc),
            "read_only": True,
        }
    try:
        observed_ref = _git_ref_oid(str(prepared["base_ref"]))
    except AtlasError as exc:
        return {
            "schema_version": "laplace.region-publication-status/1",
            "state": "UNKNOWN",
            "lease_id": lease_id,
            "publication_id": publication_id,
            "reason": f"Git ref unavailable: {exc}",
            "read_only": True,
        }
    authorization = publication.get("authorization")
    finalized = publication.get("finalized")
    candidate_commit = str(prepared["candidate_commit"])
    expected_old = str(prepared["expected_old"])
    if finalized is not None:
        state_name = "FINALIZED" if observed_ref == candidate_commit else "REFUSED"
        reason = None if state_name == "FINALIZED" else "finalized ref was rolled back or moved"
    elif observed_ref not in {expected_old, candidate_commit}:
        state_name = "REFUSED"
        reason = "base ref moved outside the prepared CAS"
    elif observed_ref == candidate_commit and authorization is None:
        state_name = "REFUSED"
        reason = "candidate appeared without durable authorization"
    else:
        state_name = (
            "AUTHORIZED"
            if authorization is not None
            else "SIGNED"
            if publication.get("signoffs")
            else "PREPARED"
        )
        reason = None
        effective = keyed.get("effective_authority")
        effective_state = (
            effective.get("effective_state") if isinstance(effective, Mapping) else "UNKNOWN"
        )
        if effective_state != "ACTIVE":
            state_name, reason = "REFUSED", f"lease authority is {effective_state}"
    return {
        "schema_version": "laplace.region-publication-status/1",
        "state": state_name,
        "reason": reason,
        "lease_id": lease_id,
        "publication_id": publication_id,
        "observed_ref": observed_ref,
        "recovery_required": (
            authorization is not None
            and finalized is None
            and observed_ref == candidate_commit
        ),
        "saga": dict(publication),
        "read_metrics": keyed["read_metrics"],
        "integrity_boundary": keyed["integrity_boundary"],
        "read_only": True,
    }


def prepare_region_publication(
    *,
    lease_id: str,
    seat_id: str,
    holder_ref: str,
    function: str,
    base_ref: str,
    affected_roots: Mapping[str, str],
    rehearsal_evidence_root: str,
    message: str,
    evidence: Mapping[str, str],
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Build an unreachable private-index candidate and durably prepare its recovery."""

    named_evidence = {str(key): str(value) for key, value in evidence.items()}
    if not named_evidence or any(not key or not value for key, value in named_evidence.items()):
        raise StateTransitionRefused("publication prepare requires named exact evidence")
    rehearsal_root = _publication_sha256(
        rehearsal_evidence_root, field="rehearsal_evidence_root"
    )
    typed_roots = {
        str(root_type): _publication_sha256(str(root), field=f"affected_roots.{root_type}")
        for root_type, root in dict(affected_roots).items()
    }
    if not typed_roots:
        raise StateTransitionRefused(
            "publication prepare requires affected typed roots", state="REFUSED"
        )
    affected_frontier_root = region_publication_affected_frontier_root(typed_roots)
    store = _store()
    state = store.current_state()
    lease = state.region_leases.get(lease_id)
    if lease is None:
        raise StateTransitionRefused("publication prepare cites an unknown lease", state="UNKNOWN")
    checkout = lease.checkout
    claimed_function = SeatRole(function)
    if (
        checkout.seat_id != seat_id
        or checkout.holder_ref != holder_ref
        or checkout.function != claimed_function
    ):
        raise StateTransitionRefused("publication prepare mismatches its lease", state="REFUSED")
    occupancy = state.seat_occupancies.get(seat_id)
    if lease.checkin is not None:
        raise StateTransitionRefused("publication prepare cites a closed lease", state="REFUSED")
    if not lease.held_at(_now()):
        raise StateTransitionRefused("publication prepare cites an expired lease", state="REFUSED")
    if not lease.matches_occupancy(occupancy):
        raise StateTransitionRefused("publication prepare authority is displaced", state="REFUSED")
    if lease.publication is not None:
        prepared = lease.publication.prepared
        hook = prepared.forward_closure
        if (
            prepared.base_ref != base_ref
            or prepared.message != message.strip()
            or dict(prepared.evidence) != named_evidence
            or prepared.affected_frontier_root != affected_frontier_root
            or prepared.rehearsal_evidence_root != rehearsal_root
            or dict(hook.affected_roots) != typed_roots
        ):
            raise StateTransitionRefused(
                "prepared publication retry mismatches durable inputs", state="REFUSED"
            )
        return {
            "schema_version": BRIDGE_SCHEMA,
            "idempotent": True,
            "publication": lease.publication.to_dict(),
        }
    candidate = _private_index_candidate(
        checkout=checkout,
        base_ref=base_ref,
        message=message,
        evidence=named_evidence,
    )
    predecessor_event_id = state.head_event_id
    if predecessor_event_id is None:
        raise StateTransitionRefused(
            "publication prepare lacks an exact predecessor head", state="REFUSED"
        )
    finalized_projection = region_forward_closure_finalized_projection(
        lease_id=lease_id,
        seat_id=seat_id,
        holder_ref=holder_ref,
        function=claimed_function,
        base_ref=base_ref,
        expected_old=candidate["expected_old"],
        result_git_head=candidate["candidate_commit"],
        candidate_tree=candidate["candidate_tree"],
        patch_handle=candidate["patch_handle"],
        custody_handle=candidate["custody_handle"],
        affected_frontier_root=affected_frontier_root,
    )
    hook = RegionForwardClosure.reserve(
        predecessor_event_id=predecessor_event_id,
        affected_roots=typed_roots,
        expires_at=checkout.expires_at,
        finalized_projection_digest=chash(finalized_projection),
    )
    identity = {
        "schema_version": RegionPublicationPrepared.SCHEMA_VERSION,
        "lease_id": lease_id,
        "seat_id": seat_id,
        "holder_ref": holder_ref,
        "function": claimed_function.value,
        "checkout_event_id": lease.checkout_event_id,
        "binding_event_id": lease.checkout_binding_event_id,
        "provider_identity_generation": lease.checkout_provider_identity_generation,
        "candidate_commit": candidate["candidate_commit"],
        "candidate_tree": candidate["candidate_tree"],
        "committed_paths": candidate["committed_paths"],
        "patch_handle": candidate["patch_handle"],
        "custody_handle": candidate["custody_handle"],
        "affected_frontier_root": affected_frontier_root,
        "rehearsal_evidence_root": rehearsal_root,
        "forward_closure": hook.to_dict(),
        "forward_closure_root": hook.forward_closure_root,
        "base_ref": base_ref,
        "expected_old": candidate["expected_old"],
        "private_index_recipe": candidate["private_index_recipe"],
        "message": message.strip(),
        "evidence": named_evidence,
    }
    publication_id = "region-publication:" + chash(identity).removeprefix("sha256:")
    recovery_root = chash(
        {
            "schema_version": "laplace.region-publication-recovery/1",
            "publication_id": publication_id,
            "prepared": identity,
        }
    )
    prepared = RegionPublicationPrepared(
        publication_id=publication_id,
        recovery_root=recovery_root,
        function=claimed_function,
        forward_closure=hook,
        **{
            key: value
            for key, value in identity.items()
            if key not in {"schema_version", "function", "forward_closure"}
        },
    )
    event = _event(
        EventKind.REGION_PUBLICATION_PREPARED,
        prepared.to_dict(),
        actor=claimed_function,
        subject=f"publication:{publication_id}",
        provider=provider,
        model=model,
        correlation_id=_correlation(correlation_id, prepared.to_dict()),
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=tuple(
            dict.fromkeys(
                event_id
                for event_id in (
                    state.head_event_id,
                    lease.checkout_event_id,
                    lease.checkout_binding_event_id,
                )
                if event_id is not None
            )
        ),
        evidence_handles=(prepared.patch_handle, prepared.custody_handle),
        note="private-index publication candidate durably prepared without ref movement",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "idempotent": False,
        "receipt": _receipt(stored),
        "publication": store.current_state().region_leases[lease_id].publication.to_dict(),
    }


def sign_region_publication(
    *,
    lease_id: str,
    publication_id: str,
    expected_recovery_root: str,
    expected_candidate_commit: str,
    expected_candidate_tree: str,
    expected_patch_handle: str,
    expected_custody_handle: str,
    expected_affected_frontier_root: str,
    expected_rehearsal_evidence_root: str,
    expected_forward_closure_root: str,
    seat_id: str,
    holder_ref: str,
    function: str,
    role_profile_handle: str,
    reconstruction_handle: str,
    predicate_result: str,
    expires_at: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Append one role-current PASS over the exact frozen local-ref candidate."""

    store = _store()
    state = store.current_state()
    lease, publication = _publication_row(
        state, lease_id=lease_id, publication_id=publication_id
    )
    prepared = publication.prepared
    if expected_recovery_root != prepared.recovery_root:
        raise StateTransitionRefused("signoff recovery root mismatches", state="REFUSED")
    expected_candidate = {
        "candidate_commit": expected_candidate_commit,
        "candidate_tree": expected_candidate_tree,
        "patch_handle": expected_patch_handle,
        "custody_handle": expected_custody_handle,
        "affected_frontier_root": expected_affected_frontier_root,
        "rehearsal_evidence_root": expected_rehearsal_evidence_root,
        "forward_closure_root": expected_forward_closure_root,
    }
    moved = {
        key: {"expected": value, "current": getattr(prepared, key)}
        for key, value in expected_candidate.items()
        if value != getattr(prepared, key)
    }
    if moved:
        raise StateTransitionRefused(
            "publication signer judged different candidate or frontier",
            state="REFUSED",
            mismatches=moved,
        )
    if publication.authorization is not None or publication.finalized is not None:
        raise StateTransitionRefused("publication signoff follows authorization", state="REFUSED")
    claimed_function = SeatRole(function)
    expected_functions = (SeatRole.EGO, SeatRole.SENSORIUM, SeatRole.SUPEREGO)
    existing_for_role = next(
        (
            item
            for item in publication.signoffs
            if item.signoff.signer_function == claimed_function
        ),
        None,
    )
    if existing_for_role is not None:
        existing = existing_for_role.signoff
        if (
            existing.signer_seat_id == seat_id
            and existing.signer_holder_ref == holder_ref
            and existing.role_profile_handle == role_profile_handle
            and existing.reconstruction_handle == reconstruction_handle
            and existing.predicate_result == predicate_result
            and existing.expires_at == expires_at
        ):
            return {
                "schema_version": BRIDGE_SCHEMA,
                "idempotent": True,
                "signoff": existing_for_role.to_dict(),
                "publication": publication.to_dict(),
            }
        raise StateTransitionRefused("publication role already signed different bytes", state="REFUSED")
    if len(publication.signoffs) >= 3 or claimed_function != expected_functions[
        len(publication.signoffs)
    ]:
        raise StateTransitionRefused(
            "publication signoffs must be Ego then Aisthesis then Superego",
            state="REFUSED",
        )
    occupancy = state.seat_occupancies.get(seat_id)
    if (
        occupancy is None
        or not occupancy.routing_authority
        or occupancy.binding is None
        or occupancy.join.holder_ref != holder_ref
        or occupancy.join.function != claimed_function
        or occupancy.binding_event_id is None
    ):
        raise StateTransitionRefused("publication signer identity is not currently bound", state="REFUSED")
    predicate_domain = {
        SeatRole.EGO: "ego",
        SeatRole.SENSORIUM: "aisthesis",
        SeatRole.SUPEREGO: "superego",
    }[claimed_function]
    consumed = (
        tuple(item.event_id for item in publication.signoffs)
        if claimed_function == SeatRole.SUPEREGO
        else ()
    )
    identity = {
        "schema_version": RegionPublicationSignoff.SCHEMA_VERSION,
        "publication_id": publication_id,
        "lease_id": lease_id,
        "prepared_event_id": publication.prepared_event_id,
        "recovery_root": prepared.recovery_root,
        "candidate_commit": prepared.candidate_commit,
        "candidate_tree": prepared.candidate_tree,
        "patch_handle": prepared.patch_handle,
        "custody_handle": prepared.custody_handle,
        "affected_frontier_root": prepared.affected_frontier_root,
        "rehearsal_evidence_root": prepared.rehearsal_evidence_root,
        "forward_closure_root": prepared.forward_closure_root,
        "signer_seat_id": seat_id,
        "signer_holder_ref": holder_ref,
        "signer_function": claimed_function.value,
        "signer_join_event_id": occupancy.join_event_id,
        "signer_binding_event_id": occupancy.binding_event_id,
        "signer_provider_identity_generation": (
            occupancy.binding.provider_identity_generation
        ),
        "role_profile_handle": _publication_sha256(
            role_profile_handle, field="role_profile_handle"
        ),
        "reconstruction_handle": _publication_sha256(
            reconstruction_handle, field="reconstruction_handle"
        ),
        "predicate_result": predicate_result,
        "predicate_domain": predicate_domain,
        "expires_at": expires_at,
        "consumed_signoff_event_ids": list(consumed),
    }
    signoff = RegionPublicationSignoff(
        signoff_root=chash(identity),
        signer_function=claimed_function,
        consumed_signoff_event_ids=consumed,
        **{
            key: value
            for key, value in identity.items()
            if key
            not in {
                "schema_version",
                "signer_function",
                "consumed_signoff_event_ids",
            }
        },
    )
    event = _event(
        EventKind.REGION_PUBLICATION_SIGNED,
        signoff.to_dict(),
        actor=claimed_function,
        subject=f"publication:{publication_id}",
        provider=provider,
        model=model,
        correlation_id=_correlation(correlation_id, signoff.to_dict()),
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=tuple(
            dict.fromkeys(
                event_id
                for event_id in (
                    state.head_event_id,
                    publication.prepared_event_id,
                    occupancy.binding_event_id,
                    *consumed,
                )
                if event_id is not None
            )
        ),
        evidence_handles=(signoff.role_profile_handle, signoff.reconstruction_handle),
        note=f"{predicate_domain} publication predicate passed",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "idempotent": False,
        "receipt": _receipt(stored),
        "signoff": store.current_state()
        .region_leases[lease_id]
        .publication.signoffs[-1]
        .to_dict(),
        "publication": store.current_state().region_leases[lease_id].publication.to_dict(),
    }


def authorize_region_publication(
    *,
    lease_id: str,
    publication_id: str,
    expected_recovery_root: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Durably grant one exact update-ref CAS; this does not touch Git."""

    store = _store()
    state = store.current_state()
    lease, publication = _publication_row(
        state, lease_id=lease_id, publication_id=publication_id
    )
    prepared = publication.prepared
    if expected_recovery_root != prepared.recovery_root:
        raise StateTransitionRefused("authorization recovery root mismatches", state="REFUSED")
    if publication.finalized is not None:
        return {"schema_version": BRIDGE_SCHEMA, "idempotent": True, "publication": publication.to_dict()}
    if publication.authorization is not None:
        return {"schema_version": BRIDGE_SCHEMA, "idempotent": True, "publication": publication.to_dict()}
    if tuple(item.signoff.signer_function for item in publication.signoffs) != (
        SeatRole.EGO,
        SeatRole.SENSORIUM,
        SeatRole.SUPEREGO,
    ):
        raise StateTransitionRefused("publication authorization requires the exact triad", state="REFUSED")
    signoff_event_ids = tuple(item.event_id for item in publication.signoffs)
    signoff_roots = tuple(item.signoff.signoff_root for item in publication.signoffs)
    expires_at = min(
        (item.signoff.expires_at for item in publication.signoffs),
        key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
    )
    if _parsed_time(expires_at) > _parsed_time(prepared.forward_closure.expires_at):
        raise StateTransitionRefused(
            "publication authorization outlives its forward closure",
            state="REFUSED",
        )
    identity = {
        "schema_version": RegionPublicationAuthorization.SCHEMA_VERSION,
        "publication_id": publication_id,
        "lease_id": lease_id,
        "prepared_event_id": publication.prepared_event_id,
        "recovery_root": prepared.recovery_root,
        "base_ref": prepared.base_ref,
        "expected_old": prepared.expected_old,
        "candidate_commit": prepared.candidate_commit,
        "affected_frontier_root": prepared.affected_frontier_root,
        "rehearsal_evidence_root": prepared.rehearsal_evidence_root,
        "forward_closure_root": prepared.forward_closure_root,
        "signoff_event_ids": list(signoff_event_ids),
        "signoff_roots": list(signoff_roots),
        "expires_at": expires_at,
        "cas_permission": "UPDATE-REF-ONCE",
    }
    authorization = RegionPublicationAuthorization(
        authorization_root=chash(identity),
        signoff_event_ids=signoff_event_ids,
        signoff_roots=signoff_roots,
        **{
            key: value
            for key, value in identity.items()
            if key not in {"schema_version", "signoff_event_ids", "signoff_roots"}
        },
    )
    event = _event(
        EventKind.REGION_PUBLICATION_AUTHORIZED,
        authorization.to_dict(),
        actor=lease.checkout.function,
        subject=f"publication:{publication_id}",
        provider=provider,
        model=model,
        correlation_id=_correlation(correlation_id, authorization.to_dict()),
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=tuple(
            dict.fromkeys(
                event_id
                for event_id in (
                    state.head_event_id,
                    publication.prepared_event_id,
                    lease.checkout_binding_event_id,
                    *signoff_event_ids,
                )
                if event_id is not None
            )
        ),
        note="exact local-ref CAS authorized by Ego, Aisthesis, and Superego",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "idempotent": False,
        "receipt": _receipt(stored),
        "publication": store.current_state().region_leases[lease_id].publication.to_dict(),
    }


def finalize_region_publication(
    *,
    lease_id: str,
    publication_id: str,
    expected_recovery_root: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Consume one authorization with ref CAS and atomic FINALIZED+CHECKIN append."""

    store = _store()
    state = store.current_state()
    lease, publication = _publication_row(
        state, lease_id=lease_id, publication_id=publication_id
    )
    prepared = publication.prepared
    authorization = publication.authorization
    if expected_recovery_root != prepared.recovery_root:
        raise StateTransitionRefused("finalize recovery root mismatches", state="REFUSED")
    if publication.finalized is not None:
        status = region_publication(lease_id=lease_id, publication_id=publication_id)
        if status["state"] != "FINALIZED":
            raise StateTransitionRefused(status["reason"], state="REFUSED")
        return {"schema_version": BRIDGE_SCHEMA, "idempotent": True, **status}
    if authorization is None or publication.authorized_event_id is None:
        raise StateTransitionRefused("publication finalize lacks authorization", state="REFUSED")
    consumption_root = region_forward_closure_consumption_root(
        forward_closure_root=prepared.forward_closure_root,
        authorized_event_id=publication.authorized_event_id,
        finalized_projection_digest=(
            prepared.forward_closure.finalized_projection_digest
        ),
    )
    finalized = RegionPublicationFinalized(
        publication_id=publication_id,
        lease_id=lease_id,
        prepared_event_id=publication.prepared_event_id,
        authorized_event_id=publication.authorized_event_id,
        recovery_root=prepared.recovery_root,
        authorization_root=authorization.authorization_root,
        base_ref=prepared.base_ref,
        expected_old=prepared.expected_old,
        result_git_head=prepared.candidate_commit,
        candidate_tree=prepared.candidate_tree,
        patch_handle=prepared.patch_handle,
        custody_handle=prepared.custody_handle,
        affected_frontier_root=prepared.affected_frontier_root,
        forward_closure_root=prepared.forward_closure_root,
        forward_closure_consumption_root=consumption_root,
        signoff_roots=authorization.signoff_roots,
    )
    finalized_event = _event(
        EventKind.REGION_PUBLICATION_FINALIZED,
        finalized.to_dict(),
        actor=lease.checkout.function,
        subject=f"publication:{publication_id}",
        provider=provider,
        model=model,
        correlation_id=_correlation(correlation_id, finalized.to_dict()),
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=tuple(
            dict.fromkeys(
                event_id
                for event_id in (state.head_event_id, publication.authorized_event_id)
                if event_id is not None
            )
        ),
        evidence_handles=(prepared.patch_handle, prepared.custody_handle),
        note="authorized Git ref CAS finalized",
    )
    checkin = RegionCheckin(
        lease_id=lease_id,
        seat_id=prepared.seat_id,
        holder_ref=prepared.holder_ref,
        function=prepared.function,
        outcome=LeaseCheckinOutcome.COMMITTED,
        base_git_head=lease.checkout.base_git_head,
        result_git_head=prepared.candidate_commit,
        committed_paths=prepared.committed_paths,
        dirty_paths=(),
        evidence={
            **dict(prepared.evidence),
            "publication_patch": prepared.patch_handle,
            "publication_custody": prepared.custody_handle,
            "publication_recovery": prepared.recovery_root,
            "publication_authorization": authorization.authorization_root,
            "publication_triad": chash(
                {
                    "schema_version": "laplace.region-publication-triad/1",
                    "signoff_event_ids": list(authorization.signoff_event_ids),
                    "signoff_roots": list(authorization.signoff_roots),
                }
            ),
            "affected_frontier_root": prepared.affected_frontier_root,
            "rehearsal_evidence_root": prepared.rehearsal_evidence_root,
            "forward_closure_consumed": consumption_root,
            "publication_scope": "LOCAL_REF_ONLY",
        },
    )
    checkin_event = _event(
        EventKind.REGION_CHECKIN,
        checkin.to_dict(),
        actor=lease.checkout.function,
        subject=f"lease:{lease_id}",
        provider=provider,
        model=model,
        correlation_id=_correlation(correlation_id, checkin.to_dict()),
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=tuple(
            dict.fromkeys(
                event_id
                for event_id in (
                    finalized_event.event_id,
                    lease.checkout_event_id,
                    lease.checkout_binding_event_id,
                )
                if event_id is not None
            )
        ),
        evidence_handles=(prepared.patch_handle, prepared.custody_handle),
        note="publication finalized and region lease checked in atomically",
    )
    stored = store.finalize_region_publication(
        (finalized_event, checkin_event),
        ref_cas=lambda: _git_update_ref_once(
            base_ref=prepared.base_ref,
            expected_old=prepared.expected_old,
            candidate_commit=prepared.candidate_commit,
        ),
    )
    return {
        "schema_version": BRIDGE_SCHEMA,
        "idempotent": False,
        "receipts": [_receipt(row) for row in stored],
        "publication": store.current_state().region_leases[lease_id].publication.to_dict(),
    }


def recover_region_publication(
    *,
    lease_id: str,
    publication_id: str,
    expected_recovery_root: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Complete the same authorized saga after either crash boundary, or refuse."""

    status = region_publication(lease_id=lease_id, publication_id=publication_id)
    if status["state"] == "FINALIZED":
        return {"schema_version": BRIDGE_SCHEMA, "idempotent": True, **status}
    if status["state"] != "AUTHORIZED":
        raise StateTransitionRefused(
            "publication recovery refuses without one current durable authorization",
            state=status["state"],
            reason=status.get("reason"),
        )
    return finalize_region_publication(
        lease_id=lease_id,
        publication_id=publication_id,
        expected_recovery_root=expected_recovery_root,
        provider=provider,
        model=model,
        correlation_id=correlation_id,
    )


def publish_regions(
    *,
    lease_id: str,
    seat_id: str,
    holder_ref: str,
    function: str,
    message: str,
    evidence: Mapping[str, str],
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Finalize only an already prepared, triad-signed, local-ref authorization."""

    store = _store()
    state = store.current_state()
    lease = state.region_leases.get(lease_id)
    if lease is None:
        raise StateTransitionRefused("region publication cites an unknown lease", state="UNKNOWN")
    checkout = lease.checkout
    claimed_function = SeatRole(function)
    if (
        checkout.seat_id != seat_id
        or checkout.holder_ref != holder_ref
        or checkout.function != claimed_function
    ):
        raise StateTransitionRefused(
            "region publication does not match its checkout authority", state="REFUSED"
        )
    if lease.checkin is not None:
        if lease.publication is not None and lease.publication.finalized is not None:
            return {
                "schema_version": BRIDGE_SCHEMA,
                "idempotent": True,
                **region_publication(
                    lease_id=lease_id,
                    publication_id=lease.publication.prepared.publication_id,
                ),
            }
        raise StateTransitionRefused("region publication cites a closed lease", state="REFUSED")
    publication = lease.publication
    if (
        publication is None
        or publication.authorization is None
        or len(publication.signoffs) != 3
    ):
        raise StateTransitionRefused(
            "region publication requires PREPARED, triad-SIGNED, and AUTHORIZED",
            state="REFUSED",
        )
    prepared = publication.prepared
    if not prepared.base_ref.startswith("refs/heads/"):
        raise StateTransitionRefused("publication is not LOCAL_REF_ONLY", state="REFUSED")
    if message.strip() != prepared.message:
        raise StateTransitionRefused("publication message moved after prepare", state="REFUSED")
    named_evidence = {str(key): str(value) for key, value in evidence.items()}
    if named_evidence != dict(prepared.evidence):
        raise StateTransitionRefused("publication evidence moved after prepare", state="REFUSED")
    return finalize_region_publication(
        lease_id=lease_id,
        publication_id=prepared.publication_id,
        expected_recovery_root=prepared.recovery_root,
        provider=provider,
        model=model,
        correlation_id=correlation_id,
    )


def region_leases(*, as_of: str = "") -> dict[str, Any]:
    """Serve current scoped authority with expiry evaluated at the caller's exact time."""

    observed_at = as_of.strip() or _now()
    state = _read_store().current_state()
    leases: dict[str, Any] = {}
    for lease_id, lease in sorted(state.region_leases.items()):
        leases[lease_id] = _project_region_lease(lease, observed_at, state=state)
    return {
        "schema_version": "laplace.region-leases/1",
        "observed_at": observed_at,
        "leases": leases,
        "active": [key for key, value in leases.items() if value["write_authority"]],
        "read_only": True,
    }


def _project_region_lease(
    lease: Any,
    observed_at: str,
    *,
    state: ConceptricState | None = None,
) -> dict[str, Any]:
    """Render one time-dependent authority face without changing folded history."""

    row = effective_region_lease_projection(
        lease,
        seat_occupancies=None if state is None else state.seat_occupancies,
        observed_at=observed_at,
    )
    if lease.checkout.bootstrap_crutch is not None and state is not None:
        row["bootstrap_crutch_retirement"] = bootstrap_crutch_retirement(
            state,
            lease.checkout.bootstrap_crutch,
        )
    return row


def select_context(
    *,
    assumption: str,
    fibre: str,
    provider: str,
    model: str,
    confidence: float | None = None,
    alternatives: tuple[str, ...] = (),
    correlation_id: str = "",
) -> dict[str, Any]:
    """Select the first assumption fibre; changing it requires ``transport_context``."""

    store = _store()
    state = store.current_state()
    if (state.active_assumption, state.active_fibre) == (assumption, fibre):
        return {
            "schema_version": BRIDGE_SCHEMA,
            "changed": False,
            "active_context": {"assumption": assumption, "fibre": fibre},
        }
    if state.active_assumption is not None:
        raise StateTransitionRefused(
            "active assumption fibre can change only through an explicit transport",
            active_assumption=state.active_assumption,
            active_fibre=state.active_fibre,
        )
    selection = AssumptionSelection(assumption, fibre, confidence, alternatives)
    correlation = _correlation(
        correlation_id, {"assumption": assumption, "fibre": fibre, "head": state.head_event_id}
    )
    event = _event(
        EventKind.ASSUMPTION,
        selection.to_dict(),
        actor=SeatRole.SYSTEM,
        subject=f"assumption:{assumption}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=assumption,
        fibre=fibre,
        note="initial provider assumption fibre selected",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "changed": True,
        "receipt": _receipt(stored),
        "active_context": {"assumption": assumption, "fibre": fibre},
    }


def transport_context(
    *,
    assumption: str,
    fibre: str,
    operator: str,
    loss_or_obstruction: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Move to a different assumption fibre with a typed, inspectable transport receipt."""

    store = _store()
    state = store.current_state()
    from_assumption, from_fibre = _context(state)
    if (from_assumption, from_fibre) == (assumption, fibre):
        raise StateTransitionRefused("transport endpoints must differ")
    transport_id = chash(
        {
            "from_assumption": from_assumption,
            "from_fibre": from_fibre,
            "to_assumption": assumption,
            "to_fibre": fibre,
            "operator": operator,
            "loss_or_obstruction": loss_or_obstruction,
            "head": state.head_event_id,
        }
    )
    payload = TransportReceipt(
        transport_id,
        from_assumption,
        assumption,
        from_fibre,
        fibre,
        operator,
        loss_or_obstruction,
    )
    correlation = _correlation(correlation_id, {"transport_id": transport_id})
    event = _event(
        EventKind.TRANSPORT,
        payload.to_dict(),
        actor=SeatRole.SYSTEM,
        subject=f"transport:{transport_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=assumption,
        fibre=fibre,
        causation_ids=() if state.head_event_id is None else (state.head_event_id,),
        note=f"explicit assumption-fibre transport via {operator}",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "receipt": _receipt(stored),
        "transport_id": transport_id,
        "active_context": {"assumption": assumption, "fibre": fibre},
    }


def send(
    *,
    sender_seat_id: str,
    recipient_seat_id: str,
    message_type: str,
    body: str,
    dependency_roots: Mapping[str, str],
    idempotency_key: str,
    expires_at: str,
    provider: str,
    model: str,
    correlation_id: str = "",
    causation_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Queue one deterministic message, retrying only proved pre-append contention.

    ``StoreLockTimeout`` means the authority lock was never acquired and the protected write
    body did not run.  Retrying the same content/idempotency identity is therefore exact.  Every
    other store failure remains loud because it may describe an ambiguous or committed outcome;
    the append-proof/status path in ``_send_once`` handles the one known post-commit seam.
    """

    arguments = {
        "sender_seat_id": sender_seat_id,
        "recipient_seat_id": recipient_seat_id,
        "message_type": message_type,
        "body": body,
        "dependency_roots": dependency_roots,
        "idempotency_key": idempotency_key,
        "expires_at": expires_at,
        "provider": provider,
        "model": model,
        "correlation_id": correlation_id,
        "causation_ids": causation_ids,
    }
    for attempt in range(2):
        try:
            return _send_once(**arguments)
        except StoreLockTimeout:
            if attempt:
                raise
            # A cached store may carry a head from before the contender committed.  The retry
            # reconstructs current authority rather than asking that stale instance to guess.
            _store_at.cache_clear()
            time.sleep(0.05)
    raise AssertionError("bounded Fabric send retry exhausted without returning or raising")


def _send_once(
    *,
    sender_seat_id: str,
    recipient_seat_id: str,
    message_type: str,
    body: str,
    dependency_roots: Mapping[str, str],
    idempotency_key: str,
    expires_at: str,
    provider: str,
    model: str,
    correlation_id: str = "",
    causation_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Attempt to store a body and queue its typed handle; queued is not delivery."""

    if _DEPENDENCY_FRESHNESS_ROOT in dependency_roots:
        raise StateTransitionRefused(
            "dependency freshness is computed by Fabric and cannot be caller-authored"
        )
    # Bind the store and its provider-body custody as one authority capability.  Resolving
    # ``LAPLACE_STATE`` separately for put/check/append recreates the two-root race this door is
    # meant to forbid; no environment change after this line can move either half of the act.
    store = _store()
    blobs = BlobStore(store.root / "blobs")
    body_handle = blobs.put(body.encode("utf-8"))
    # CONTENT BEFORE COMMITMENT (superego, fabric #987, item b). custody_has has existed
    # at atlas_bridge.py since it was written and was never called on this path, so a send
    # could queue a handle whose bytes had landed in a different store — which is exactly
    # how three unresolvable author-acts reached the ledger. The put and this check resolve
    # the SAME _blobs() root, so a split between them is caught here instead of by a reader
    # hours later, or by a custody snapshot refusing the whole fabric.
    try:
        blobs.get(body_handle)
    except (BlobMissing, BlobHashMismatch) as exc:
        raise StateTransitionRefused(
            "the message body did not land in the custody this send will cite",
            body_handle=body_handle,
            blobs=str(blobs.root),
        ) from exc
    roots = dict(dependency_roots)
    declared_body = roots.get("body")
    if declared_body is not None and declared_body != body_handle:
        raise StateTransitionRefused(
            "body dependency root disagrees with the exact stored message body",
            declared=declared_body,
            stored=body_handle,
        )
    roots["body"] = body_handle
    # Identity binds only the caller's declared roots.  The observation is stored beside them
    # but excluded from message identity, so an idempotent retry after Git moves still resolves
    # to the original message rather than manufacturing a second envelope.
    declared_roots = dict(roots)
    send_freshness = _dependency_freshness(declared_roots)
    if send_freshness["known_root_count"]:
        roots[_DEPENDENCY_FRESHNESS_ROOT] = json.dumps(
            send_freshness, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    identity = {
        "sender": sender_seat_id,
        "recipient": recipient_seat_id,
        "message_type": message_type,
        "body_handle": body_handle,
        "dependency_roots": declared_roots,
        "idempotency_key": idempotency_key,
        "expires_at": expires_at,
    }
    message_id = "message:" + chash(identity).removeprefix("sha256:")
    correlation = _correlation(correlation_id, identity)
    for _attempt in range(8):
        state = store.current_state()
        assumption, fibre = _context(state)
        actor = _seat_role(state, sender_seat_id)
        _seat_role(state, recipient_seat_id)
        prior_message_id = state.message_idempotency.get(idempotency_key)
        if prior_message_id is not None:
            if prior_message_id != message_id:
                raise StateTransitionRefused(
                    "idempotency key already names different message content",
                    prior_message_id=prior_message_id,
                )
            prior = state.messages[prior_message_id]
            prior_status = _status_with_dependency_freshness(prior.to_dict())
            return {
                "schema_version": BRIDGE_SCHEMA,
                "idempotent": True,
                "message_id": prior_message_id,
                "body_handle": body_handle,
                "status": prior_status,
                "dependency_freshness": prior_status["dependency_freshness"],
                "status_observation": {
                    "state": "known",
                    "error": None,
                    "append_proof": prior.sent_event_id,
                },
            }
        message = SeatMessage(
            message_id,
            sender_seat_id,
            recipient_seat_id,
            message_type,
            body_handle,
            roots,
            idempotency_key,
            state.event_count + 1,
            expires_at,
        )
        event = _event(
            EventKind.MESSAGE,
            message.to_dict(),
            actor=actor,
            subject=message_id,
            provider=provider,
            model=model,
            correlation_id=correlation,
            assumption=assumption,
            fibre=fibre,
            causation_ids=causation_ids,
            body_handle=body_handle,
            note="provider message queued; no delivery claimed",
        )
        try:
            stored = store.append(event)
        except StateTransitionRefused as exc:
            if "message cursor must equal" in str(exc):
                continue
            raise
        try:
            status = _status_with_dependency_freshness(store.message_status(message_id))
            status_observation = {
                "state": "known",
                "error": None,
                "append_proof": stored.event.event_id,
            }
        except Exception as exc:  # noqa: BLE001 - append proof outranks a failed readback
            # The event is already durably appended.  Raising here used to make callers record
            # the recipient as unreached even though the message existed in Atlas.  The readback
            # is useful detail, never authority over the append receipt.
            status = None
            status_observation = {
                "state": "unknown-after-append",
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
                "append_proof": stored.event.event_id,
            }
        return {
            "schema_version": BRIDGE_SCHEMA,
            "idempotent": False,
            "message_id": message_id,
            "body_handle": body_handle,
            "media_type": BODY_MEDIA_TYPE,
            "receipt": _receipt(stored),
            "status": status,
            "dependency_freshness": (
                status.get("dependency_freshness")
                if status is not None
                else {"send": send_freshness, "current": None}
            ),
            "status_observation": status_observation,
        }
    raise StateTransitionRefused("message send lost eight consecutive cursor races")


def pull(
    *,
    seat_id: str,
    as_of: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Bank the seat's deterministic cursor advance and return verified message bodies."""

    as_of = as_of.strip() or _now()
    store = _store()
    blobs = BlobStore(store.root / "blobs")
    for _attempt in range(8):
        state = store.current_state()
        assumption, fibre = _context(state)
        actor = _seat_role(state, seat_id)
        after_cursor = state.cursor_for(seat_id)
        pending = state.pending_messages(seat_id, after_cursor=after_cursor, as_of=as_of)
        # CONTENT BEFORE CURSOR.  The old order banked the whole deterministic pull and only
        # then opened bodies; one missing blob raised after the cursor had advanced, so a retry
        # returned an empty inbox and every good neighbour vanished from attention.  Preflight
        # every named body against the SAME bound root.  An unreadable row returns typed UNKNOWN,
        # leaves every message queued, and does not append a pull event.
        verified: dict[str, str] = {}
        unknown: list[dict[str, Any]] = []
        for message in pending:
            try:
                verified[message.message_id] = blobs.get(message.body_handle).decode("utf-8")
            except (BlobMissing, BlobHashMismatch, UnicodeDecodeError) as exc:
                unknown.append(
                    {
                        "schema_version": "laplace.fabric-content-residue/1",
                        "message_id": message.message_id,
                        "cursor": message.cursor,
                        "body_handle": message.body_handle,
                        "status": "UNKNOWN",
                        "reason": getattr(exc, "reason", type(exc).__name__),
                        "error": str(exc),
                        "guidance": (
                            "recover or retract this exact envelope before pulling the seat; "
                            "the durable cursor has not moved"
                        ),
                    }
                )
        if unknown:
            return {
                "schema_version": BRIDGE_SCHEMA,
                "receipt": None,
                "status": "BLOCKED-UNKNOWN-CONTENT",
                "seat_id": seat_id,
                "after_cursor": after_cursor,
                "result_cursor": after_cursor,
                "cursor_advanced": False,
                "messages": [],
                "pending_count": len(pending),
                "readable_message_ids": [
                    message.message_id for message in pending if message.message_id in verified
                ],
                "unknown_content": unknown,
                "delivery_claim": "none; no pull event was banked",
            }
        pull_row = MessagePull(
            seat_id,
            after_cursor,
            state.event_count,
            as_of,
            tuple(message.message_id for message in pending),
        )
        correlation = _correlation(
            correlation_id,
            {
                "seat_id": seat_id,
                "after_cursor": after_cursor,
                "result_cursor": state.event_count,
                "as_of": as_of,
            },
        )
        event = _event(
            EventKind.MESSAGE_PULL,
            pull_row.to_dict(),
            actor=actor,
            subject=f"pull:{seat_id}:{state.event_count}",
            provider=provider,
            model=model,
            correlation_id=correlation,
            assumption=assumption,
            fibre=fibre,
            causation_ids=tuple(state.messages[m.message_id].sent_event_id for m in pending),
            note="provider pull cursor and result banked",
        )
        try:
            stored = store.append(event)
        except StateTransitionRefused as exc:
            if "pull result cursor" in str(exc) or "durable cursor" in str(exc):
                continue
            raise
        messages = [
            {
                **message.to_dict(),
                "body": verified[message.message_id],
                "media_type": BODY_MEDIA_TYPE,
                "dependency_freshness": _message_dependency_freshness(message.dependency_roots),
            }
            for message in pending
        ]
        return {
            "schema_version": BRIDGE_SCHEMA,
            "receipt": _receipt(stored),
            "seat_id": seat_id,
            "after_cursor": after_cursor,
            "result_cursor": pull_row.result_cursor,
            "cursor_advanced": True,
            "messages": messages,
        }
    raise StateTransitionRefused("message pull lost eight consecutive cursor races")


def reconstruct(
    *,
    message_id: str,
    seat_id: str,
    goal: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Materialize a pulled body and bank the typed proof required for delivery."""

    store = _store()
    state = store.current_state()
    actor = _seat_role(state, seat_id)
    record = state.messages.get(message_id)
    if record is None:
        raise StateTransitionRefused("reconstruction cites unknown message")
    if record.message.recipient_seat_id != seat_id:
        raise StateTransitionRefused("only the recipient seat may reconstruct a message")
    if record.status.value != "pulled":
        raise StateTransitionRefused(
            "message must be durably pulled before reconstruction",
            status=record.status.value,
        )
    assumption, fibre = _context(state)
    if (assumption, fibre) != (record.assumption, record.fibre):
        raise StateTransitionRefused("reconstruction cannot cross the message's assumption fibre")
    body = _blobs().get(record.message.body_handle).decode("utf-8")
    reconstruction_handle = chash(
        {
            "message_id": message_id,
            "seat_id": seat_id,
            "goal": goal,
            "body_handle": record.message.body_handle,
            "assumption": assumption,
            "fibre": fibre,
        }
    )
    evaluation_id = "reconstruction:" + reconstruction_handle.removeprefix("sha256:")
    dependencies = dict(record.message.dependency_roots)
    dependencies["send_event"] = record.sent_event_id
    if record.last_pull_event_id is not None:
        dependencies["pull_event"] = record.last_pull_event_id
    evaluation = ReplEvaluation(
        evaluation_id,
        ReplOperation.RECONSTRUCT,
        (record.message.body_handle,),
        dependencies,
        {"goal": goal, "message_id": message_id},
        (reconstruction_handle,),
        seat_id,
        None,
    )
    causes = tuple(
        cause for cause in (record.sent_event_id, record.last_pull_event_id) if cause is not None
    )
    correlation = _correlation(
        correlation_id, {"message_id": message_id, "reconstruction": reconstruction_handle}
    )
    event = _event(
        EventKind.REPL,
        evaluation.to_dict(),
        actor=actor,
        subject=evaluation_id,
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=assumption,
        fibre=fibre,
        causation_ids=causes,
        body_handle=record.message.body_handle,
        note="message body verified and reconstructed into a typed handle",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "receipt": _receipt(stored),
        "message_id": message_id,
        "body": body,
        "body_handle": record.message.body_handle,
        "reconstruction_event_id": stored.event.event_id,
        "reconstruction_handle": reconstruction_handle,
        "assumption": assumption,
        "fibre": fibre,
    }


def acknowledge(
    *,
    message_id: str,
    seat_id: str,
    disposition: str,
    note: str,
    provider: str,
    model: str,
    reconstruction_event_id: str | None = None,
    reconstruction_handle: str | None = None,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Bank acceptance/refusal; acceptance is delivery only with the exact typed proof."""

    store = _store()
    state = store.current_state()
    actor = _seat_role(state, seat_id)
    record = state.messages.get(message_id)
    if record is None:
        raise StateTransitionRefused("acknowledgement cites unknown message")
    assumption, fibre = _context(state)
    acknowledgement = MessageAcknowledgement(
        message_id,
        seat_id,
        AcknowledgementDisposition(disposition),
        reconstruction_handle,
        reconstruction_event_id,
        note,
    )
    causes = [record.sent_event_id]
    if reconstruction_event_id is not None:
        causes.append(reconstruction_event_id)
    correlation = _correlation(
        correlation_id, {"message_id": message_id, "disposition": disposition}
    )
    event = _event(
        EventKind.MESSAGE_ACK,
        acknowledgement.to_dict(),
        actor=actor,
        subject=f"ack:{message_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=assumption,
        fibre=fibre,
        causation_ids=tuple(causes),
        note=f"recipient acknowledgement {disposition}",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "receipt": _receipt(stored),
        "message_id": message_id,
        "status": store.message_status(message_id),
    }


def preserve_message_fork(
    *,
    seat_id: str,
    message_id: str,
    original_sender_seat_id: str,
    recipient_seat_id: str,
    body_handle: str,
    author_ruling_ref: str,
    authority_event_id: str,
    reason: str,
    reopen_condition: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Quarantine one author-ruled cross-fibre obligation without claiming delivery."""

    store = _store()
    state = store.current_state()
    if seat_id != "superego-seat":
        raise StateTransitionRefused("only superego-seat may preserve a message fork")
    actor = _seat_role(state, seat_id)
    occupancy = state.seat_occupancies.get(seat_id)
    if (
        actor != SeatRole.SUPEREGO
        or occupancy is None
        or not occupancy.routing_authority
        or occupancy.join.function != SeatRole.SUPEREGO
    ):
        raise StateTransitionRefused(
            "fork preservation requires bound routing-authoritative Superego occupancy"
        )
    if message_id != PRESERVE_FORK_TARGET_MESSAGE_ID:
        raise StateTransitionRefused("fork preservation target is not the author-ruled row")
    if author_ruling_ref != PRESERVE_FORK_AUTHOR_RULING_REF:
        raise StateTransitionRefused("fork preservation cites the wrong author ruling")
    if authority_event_id != PRESERVE_FORK_AUTHORITY_EVENT_ID:
        raise StateTransitionRefused("fork preservation cites the wrong authority event")
    caller_identity = _authenticated_provider_identity(
        store=store,
        seat_id=seat_id,
        occupancy=occupancy,
        authority_cursor=state.event_count,
        authority_head_event_id=state.head_event_id,
    )
    record = state.messages.get(message_id)
    if record is None:
        raise StateTransitionRefused("fork preservation cites unknown message")
    if record.status.value == "quarantined":
        prior = record.preserve_fork
        if prior is None or (
            prior.message_id,
            prior.original_sender_seat_id,
            prior.recipient_seat_id,
            prior.body_handle,
            prior.author_ruling_ref,
            prior.authority_event_id,
            prior.reason,
            prior.reopen_condition,
            prior.actor_provider_session_ref,
            prior.actor_provider_identity_generation,
        ) != (
            message_id,
            original_sender_seat_id,
            recipient_seat_id,
            body_handle,
            author_ruling_ref,
            authority_event_id,
            reason,
            reopen_condition,
            caller_identity["provider_session_ref"],
            caller_identity["provider_identity_generation"],
        ):
            raise StateTransitionRefused(
                "message fork was preserved under different pinned evidence"
            )
        assert record.preserve_fork_event_id is not None
        return {
            "schema_version": BRIDGE_SCHEMA,
            "idempotent": True,
            "receipt": {
                "event_id": record.preserve_fork_event_id,
                "kind": EventKind.MESSAGE_PRESERVE_FORK.value,
            },
            "message_id": message_id,
            "status": _status_with_dependency_freshness(record.to_dict()),
        }
    preservation = MessageForkPreservation(
        message_id=message_id,
        original_sender_seat_id=original_sender_seat_id,
        recipient_seat_id=recipient_seat_id,
        body_handle=body_handle,
        author_ruling_ref=author_ruling_ref,
        authority_event_id=authority_event_id,
        reason=reason,
        reopen_condition=reopen_condition,
        actor_provider_session_ref=caller_identity["provider_session_ref"],
        actor_provider_identity_proof_handle=caller_identity["provider_identity_proof_handle"],
        actor_provider_identity_generation=caller_identity["provider_identity_generation"],
    )

    assert occupancy.binding_event_id is not None
    assumption, fibre = _context(state)
    causes = tuple(
        dict.fromkeys(
            (
                record.sent_event_id,
                authority_event_id,
                occupancy.join_event_id,
                occupancy.binding_event_id,
            )
        )
    )
    correlation = _correlation(
        correlation_id,
        {
            "seat_id": seat_id,
            "message_id": message_id,
            "authority_event_id": authority_event_id,
        },
    )
    event = _event(
        EventKind.MESSAGE_PRESERVE_FORK,
        preservation.to_dict(),
        actor=actor,
        subject=f"preserve-fork:{message_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=assumption,
        fibre=fibre,
        causation_ids=causes,
        body_handle=caller_identity["provider_identity_proof_handle"],
        note="author-ruled cross-fibre obligation preserved in reopenable quarantine",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "idempotent": False,
        "receipt": _receipt(stored),
        "message_id": message_id,
        "status": store.message_status(message_id),
    }


def supersede_message(
    *,
    message_id: str,
    sender_seat_id: str,
    replacement_message_ids: tuple[str, ...],
    note: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Retire stale undelivered mail through delivered current-fibre replacements.

    This is the original-sender reissue act.  It never claims the old message was delivered: the
    old envelope remains addressable as historical evidence with terminal state ``superseded``
    and exact edges to the replacements that were reconstructed and acknowledged.  The sender's
    logical seat name is not authority; its current v2 watcher-backed occupant must authenticate
    even an otherwise-idempotent retry.
    """

    store = _store()
    state = store.current_state()
    actor = _seat_role(state, sender_seat_id)
    record = state.messages.get(message_id)
    if record is None:
        raise StateTransitionRefused("supersession cites unknown message")
    replacements = tuple(replacement_message_ids)

    occupancy = state.seat_occupancies.get(sender_seat_id)
    if (
        state.seat_lifecycle_cutover_event_id is None
        or occupancy is None
        or not occupancy.routing_authority
        or occupancy.join.function != actor
        or occupancy.binding is None
        or occupancy.binding_event_id is None
    ):
        raise StateTransitionRefused(
            "message supersession requires the bound routing-authoritative current sender occupancy"
        )
    caller_identity = _authenticated_provider_identity(
        store=store,
        seat_id=sender_seat_id,
        occupancy=occupancy,
        authority_cursor=state.event_count,
        authority_head_event_id=state.head_event_id,
    )
    current_generation = occupancy.join.provider_identity_generation
    if (
        current_generation is None
        or occupancy.binding.provider_identity_generation != current_generation
        or caller_identity["provider_identity_generation"] != current_generation
    ):
        raise StateTransitionRefused(
            "message supersession requires the sender's exact current v2 provider generation",
            joined_generation=current_generation,
            binding_generation=occupancy.binding.provider_identity_generation,
            caller_generation=caller_identity["provider_identity_generation"],
        )
    if record.status.value == "superseded":
        if record.replacement_message_ids != replacements:
            raise StateTransitionRefused(
                "message was superseded by a different replacement set",
                replacement_message_ids=list(record.replacement_message_ids),
            )
        return {
            "schema_version": BRIDGE_SCHEMA,
            "idempotent": True,
            "message_id": message_id,
            "status": _status_with_dependency_freshness(record.to_dict()),
        }

    assumption, fibre = _context(state)
    causes = [
        record.sent_event_id,
        occupancy.join_event_id,
        occupancy.binding_event_id,
    ]
    supersession = MessageSupersession(
        message_id,
        sender_seat_id,
        replacements,
        note,
        provider_session_ref=caller_identity["provider_session_ref"],
        provider_identity_proof_handle=caller_identity["provider_identity_proof_handle"],
        provider_identity_generation=caller_identity["provider_identity_generation"],
    )
    for replacement_id in replacements:
        replacement = state.messages.get(replacement_id)
        if replacement is None:
            raise StateTransitionRefused(
                "supersession cites unknown replacement", replacement_id=replacement_id
            )
        causes.append(replacement.sent_event_id)
        if replacement.acknowledgement_event_id is not None:
            causes.append(replacement.acknowledgement_event_id)
    correlation = _correlation(
        correlation_id,
        {
            "message_id": message_id,
            "replacement_message_ids": list(replacements),
        },
    )
    event = _event(
        EventKind.MESSAGE_SUPERSESSION,
        supersession.to_dict(),
        actor=actor,
        subject=f"supersession:{message_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=assumption,
        fibre=fibre,
        causation_ids=tuple(causes),
        body_handle=caller_identity["provider_identity_proof_handle"],
        note="stale undelivered message retired through delivered current-fibre reissue",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "idempotent": False,
        "receipt": _receipt(stored),
        "message_id": message_id,
        "status": store.message_status(message_id),
    }


def reissue_stage_zero_migration_replacement(
    *,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Reissue the one expired stage-zero envelope from exact stored custody.

    This is intentionally not a generic clone operation.  It accepts no message, body, root,
    identity, recipient, key, or expiry from the caller.  Current watcher-backed ``codex-seat``
    authority is proved first; then the historical envelope is checked against the frozen
    coordinate and its exact body and caller-authored roots are re-used.  Any drift refuses
    before a Fabric event is appended.
    """

    store = _store()
    state = store.current_state()
    sender_seat_id = "codex-seat"
    actor = _seat_role(state, sender_seat_id)
    occupancy = state.seat_occupancies.get(sender_seat_id)
    if (
        actor != SeatRole.PROVIDER
        or state.seat_lifecycle_cutover_event_id is None
        or occupancy is None
        or not occupancy.routing_authority
        or occupancy.join.function != actor
        or occupancy.binding is None
        or occupancy.binding_event_id is None
    ):
        raise StateTransitionRefused(
            "stage-zero reissue requires bound routing-authoritative current v2 codex-seat"
        )
    live_identity = _live_provider_identity_attestation(sender_seat_id)
    joined_identity = _provider_identity_from_proof(
        store=store,
        proof_handle=occupancy.join.information_proof_handle,
    )
    if not (
        _provider_identity_pair_is_verified(
            proved=joined_identity,
            live=live_identity,
            seat_id=sender_seat_id,
            holder_ref=occupancy.join.holder_ref,
        )
        and occupancy.binding.provider_session_ref == occupancy.join.holder_ref
        and occupancy.binding.function == occupancy.join.function
        and occupancy.binding.provider_identity_proof_handle
        == occupancy.join.information_proof_handle
        and occupancy.join.provider_identity_generation
        == occupancy.binding.provider_identity_generation
        == live_identity.get("watcher_lease_generation")
    ):
        raise StateTransitionRefused(
            "stage-zero reissue is not authenticated by the exact current v2 codex-seat generation"
        )

    stale = state.messages.get(STAGE_ZERO_STALE_REPLACEMENT_MESSAGE_ID)
    if stale is None:
        raise StateTransitionRefused("stage-zero stale replacement is absent")
    if stale.status.value not in {"queued", "superseded"}:
        raise StateTransitionRefused(
            "stage-zero stale replacement has an unexpected terminal state",
            status=stale.status.value,
        )
    if (
        stale.message.sender_seat_id != sender_seat_id
        or stale.message.recipient_seat_id != "ego-seat"
        or stale.message.message_type != "legacy-six-current-fibre-consolidation"
        or stale.message.body_handle != STAGE_ZERO_STALE_REPLACEMENT_BODY_HANDLE
        or stale.message.expires_at != "2026-08-27T15:00:00Z"
        or stale.message.idempotency_key
        != "EGO-LEGACY-SIX-CURRENT-FIBRE-CONSOLIDATION-20260827-v1"
        or (stale.assumption, stale.fibre) != _context(state)
    ):
        raise StateTransitionRefused(
            "stage-zero stale replacement disagrees with its frozen migration coordinate"
        )
    if _parsed_time(_now()) >= _parsed_time(STAGE_ZERO_REISSUE_EXPIRES_AT):
        raise StateTransitionRefused(
            "stage-zero exact reissue coordinate has expired; mint a new reviewed successor"
        )

    blobs = BlobStore(store.root / "blobs")
    try:
        body_bytes = blobs.get(stale.message.body_handle)
        body = body_bytes.decode("utf-8")
    except (BlobMissing, BlobHashMismatch, UnicodeDecodeError) as exc:
        raise StateTransitionRefused(
            "stage-zero stale replacement body is unavailable or corrupt"
        ) from exc
    if hash_bytes(body_bytes) != STAGE_ZERO_STALE_REPLACEMENT_BODY_HANDLE:
        raise StateTransitionRefused("stage-zero stale replacement body hash drifted")

    roots = {
        key: value
        for key, value in stale.message.dependency_roots.items()
        if key not in {"body", _DEPENDENCY_FRESHNESS_ROOT}
    }
    identity = {
        "sender": sender_seat_id,
        "recipient": "ego-seat",
        "message_type": stale.message.message_type,
        "body_handle": stale.message.body_handle,
        "dependency_roots": {**roots, "body": stale.message.body_handle},
        "idempotency_key": STAGE_ZERO_REISSUE_IDEMPOTENCY_KEY,
        "expires_at": STAGE_ZERO_REISSUE_EXPIRES_AT,
    }
    expected_message_id = "message:" + chash(identity).removeprefix("sha256:")
    if expected_message_id != STAGE_ZERO_REISSUE_MESSAGE_ID:
        raise StateTransitionRefused(
            "stage-zero exact reissue identity disagrees with its reviewed message id",
            expected=STAGE_ZERO_REISSUE_MESSAGE_ID,
            derived=expected_message_id,
        )

    result = send(
        sender_seat_id=sender_seat_id,
        recipient_seat_id="ego-seat",
        message_type=stale.message.message_type,
        body=body,
        dependency_roots=roots,
        idempotency_key=STAGE_ZERO_REISSUE_IDEMPOTENCY_KEY,
        expires_at=STAGE_ZERO_REISSUE_EXPIRES_AT,
        provider=provider,
        model=model,
        correlation_id=correlation_id,
        causation_ids=(stale.sent_event_id,),
    )
    if (
        result.get("message_id") != STAGE_ZERO_REISSUE_MESSAGE_ID
        or result.get("body_handle") != STAGE_ZERO_STALE_REPLACEMENT_BODY_HANDLE
    ):
        raise StoreError("stage-zero reissue returned a coordinate other than the reviewed one")
    return {
        **result,
        "migration_act": "stage-zero-exact-reissue/1",
        "stale_message_id": STAGE_ZERO_STALE_REPLACEMENT_MESSAGE_ID,
        "reviewed_message_id": STAGE_ZERO_REISSUE_MESSAGE_ID,
    }


def _validated_author_turn_commission(
    *,
    store: ConceptricStore,
    authority: Any,
    operator_seat_id: str,
    expected_commission: Mapping[str, Any],
) -> tuple[str, str]:
    """Resolve one canonical front-door Gerard turn and its exact commission object."""

    author_turn_handle = authority.message.dependency_roots.get("author_turn")
    if not isinstance(author_turn_handle, str) or not author_turn_handle.strip():
        raise StateTransitionRefused(
            "migration recovery commission lacks one exact author-turn custody handle"
        )
    blobs = BlobStore(store.root / "blobs")
    try:
        author_turn_bytes = blobs.get(author_turn_handle)
        authority_body = blobs.get(authority.message.body_handle)
        author_turn = json.loads(author_turn_bytes.decode("utf-8"))
    except (BlobMissing, BlobHashMismatch, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateTransitionRefused(
            "migration recovery author turn or authority body is unavailable or corrupt"
        ) from exc
    if (
        not isinstance(author_turn, Mapping)
        or set(author_turn) != {"schema_version", "row"}
        or author_turn.get("schema_version") != "laplace.author-turn/1"
        or canonical_json(author_turn).encode("utf-8") != author_turn_bytes
    ):
        raise StateTransitionRefused(
            "migration recovery authority is not canonical author-turn custody"
        )
    row = author_turn.get("row")
    if (
        not isinstance(row, Mapping)
        or row.get("schema_version") != "laplace.author-turn/1"
        or row.get("record") != "talk"
        or row.get("actor") != "gerard"
        or row.get("via") != "front-door"
        or operator_seat_id not in row.get("recipient_seat_ids", ())
    ):
        raise StateTransitionRefused(
            "migration recovery author turn does not prove Gerard's front-door commission "
            "to current Superego"
        )
    text = row.get("text")
    if not isinstance(text, str) or authority_body != text.encode("utf-8"):
        raise StateTransitionRefused(
            "migration recovery message body contradicts its banked author turn"
        )
    try:
        commission = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StateTransitionRefused(
            "migration recovery author turn must contain one canonical commission object"
        ) from exc
    if (
        not isinstance(commission, Mapping)
        or canonical_json(commission) != text
        or dict(commission) != dict(expected_commission)
    ):
        raise StateTransitionRefused(
            "migration recovery author turn does not bind the exact recovery coordinate",
            required=dict(expected_commission),
        )
    return author_turn_handle, chash(commission)


def recover_legacy_message_bundle(
    *,
    actor_seat_id: str,
    replacement_message_id: str,
    authority_acknowledgement_event_id: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Atomically retire one derived historical bundle under a typed author commission.

    This migration-only lane never impersonates the historical sender and accepts no caller-
    supplied predecessor ids.  The old bundle is derived bijectively from one already-delivered
    replacement's ``source_N`` roots and typed materializations.  A current bound v2 Superego may
    perform the transition only after it has reconstructed and acknowledged a post-binding author
    commission that names the exact capsule, replacement body and derived manifest root.
    """

    store = _store()
    state = store.current_state()
    if actor_seat_id != "superego-seat":
        raise StateTransitionRefused("message migration recovery is reserved to superego-seat")
    actor = _seat_role(state, actor_seat_id)
    occupancy = state.seat_occupancies.get(actor_seat_id)
    if (
        actor != SeatRole.SUPEREGO
        or state.seat_lifecycle_cutover_event_id is None
        or occupancy is None
        or not occupancy.routing_authority
        or occupancy.join.function != SeatRole.SUPEREGO
        or occupancy.binding is None
        or occupancy.binding_event_id is None
    ):
        raise StateTransitionRefused(
            "message migration recovery requires bound routing-authoritative current v2 Superego"
        )
    caller_identity = _authenticated_provider_identity(
        store=store,
        seat_id=actor_seat_id,
        occupancy=occupancy,
        authority_cursor=state.event_count,
        authority_head_event_id=state.head_event_id,
    )
    current_generation = occupancy.join.provider_identity_generation
    if (
        current_generation is None
        or occupancy.binding.provider_identity_generation != current_generation
        or caller_identity["provider_identity_generation"] != current_generation
    ):
        raise StateTransitionRefused(
            "message migration recovery requires the exact current v2 Superego generation"
        )

    prior_recoveries = tuple(
        recovery
        for recovery in state.message_migration_supersessions.values()
        if recovery.replacement_message_id == replacement_message_id
    )
    if prior_recoveries:
        if len(prior_recoveries) != 1:
            raise StateTransitionRefused(
                "replacement belongs to multiple migration recovery transitions"
            )
        prior = prior_recoveries[0]
        if prior.authority_acknowledgement_event_id != authority_acknowledgement_event_id:
            raise StateTransitionRefused(
                "message migration recovery was authorized by a different commission"
            )
        return {
            "schema_version": BRIDGE_SCHEMA,
            "idempotent": True,
            "receipt": {
                "event_id": next(
                    event.event_id
                    for event in store.events()
                    if event.kind == EventKind.MESSAGE_MIGRATION_SUPERSESSION
                    and event.payload.get("recovery_manifest_root") == prior.recovery_manifest_root
                ),
                "kind": EventKind.MESSAGE_MIGRATION_SUPERSESSION.value,
            },
            "replacement_message_id": replacement_message_id,
            "recovery_manifest_root": prior.recovery_manifest_root,
            "message_ids": [entry.message_id for entry in prior.entries],
            "statuses": {
                entry.message_id: _status_with_dependency_freshness(
                    state.messages[entry.message_id].to_dict()
                )
                for entry in prior.entries
            },
            "delivery_claimed": False,
        }

    entries, reconstruction_correlation, replacement_reconstruction_event_id = (
        derive_message_migration_recovery_entries(
            state,
            replacement_message_id=replacement_message_id,
        )
    )
    replacement = state.messages[replacement_message_id]
    manifest = {
        "schema_version": MessageMigrationSupersession.MANIFEST_SCHEMA_VERSION,
        "replacement_message_id": replacement_message_id,
        "replacement_body_handle": replacement.message.body_handle,
        "reconstruction_correlation": reconstruction_correlation,
        "entries": [entry.to_dict() for entry in entries],
    }
    recovery_manifest_root = chash(manifest)

    authority_matches = tuple(
        record
        for record in state.messages.values()
        if record.acknowledgement_event_id == authority_acknowledgement_event_id
    )
    if len(authority_matches) != 1:
        raise StateTransitionRefused(
            "migration recovery authority acknowledgement does not identify one message"
        )
    authority = authority_matches[0]
    if (
        authority.status.value != "delivered"
        or authority.message.sender_seat_id != "gerard-seat"
        or authority.message.recipient_seat_id != actor_seat_id
        or authority.message.message_type != "conversation-turn"
        or (authority.assumption, authority.fibre) != (replacement.assumption, replacement.fibre)
    ):
        raise StateTransitionRefused(
            "migration recovery authority must be one delivered current-fibre Gerard author turn"
        )

    capsule_path = (
        REPO_ROOT
        / "atlas"
        / "packets"
        / "recovery"
        / "RECOVERY-CAPSULE-20260827-SUPEREGO-SENSORIUM-MIGRATION.md"
    )
    try:
        capsule_bytes = capsule_path.read_bytes()
    except OSError as exc:
        raise StateTransitionRefused("message migration recovery capsule is unavailable") from exc
    capsule_handle = hash_bytes(capsule_bytes)
    if capsule_handle != MESSAGE_MIGRATION_RECOVERY_CAPSULE_HANDLE:
        raise StateTransitionRefused(
            "message migration recovery capsule bytes disagree with the pinned coordinate",
            expected=MESSAGE_MIGRATION_RECOVERY_CAPSULE_HANDLE,
            got=capsule_handle,
        )
    expected_commission = {
        "schema_version": MessageMigrationSupersession.COMMISSION_SCHEMA_VERSION,
        "authorized_act": MessageMigrationSupersession.SCHEMA_VERSION,
        "migration_root": capsule_handle,
        "replacement_message": replacement_message_id,
        "replacement_body": replacement.message.body_handle,
        "recovery_manifest": recovery_manifest_root,
    }
    author_turn_handle, commission_handle = _validated_author_turn_commission(
        store=store,
        authority=authority,
        operator_seat_id=actor_seat_id,
        expected_commission=expected_commission,
    )
    # All refusal-only checks precede this put.  A bad commission therefore cannot leave an
    # unreferenced capsule blob behind merely by reaching the migration API.
    stored_capsule_handle = BlobStore(store.root / "blobs").put(capsule_bytes)
    if stored_capsule_handle != capsule_handle:
        raise StateTransitionRefused(
            "message migration recovery capsule did not enter exact Atlas custody"
        )

    assert state.seat_lifecycle_cutover_event_id is not None
    recovery = MessageMigrationSupersession(
        transition_id=(
            "message-migration-supersession:" + recovery_manifest_root.removeprefix("sha256:")
        ),
        entries=entries,
        reconstruction_correlation=reconstruction_correlation,
        replacement_message_id=replacement_message_id,
        replacement_body_handle=replacement.message.body_handle,
        recovery_manifest_root=recovery_manifest_root,
        lifecycle_cutover_event_id=state.seat_lifecycle_cutover_event_id,
        recovery_capsule_handle=capsule_handle,
        author_turn_handle=author_turn_handle,
        commission_handle=commission_handle,
        authority_message_id=authority.message.message_id,
        authority_body_handle=authority.message.body_handle,
        authority_acknowledgement_event_id=authority_acknowledgement_event_id,
        operator_seat_id=actor_seat_id,
        operator_provider_session_ref=caller_identity["provider_session_ref"],
        operator_provider_identity_proof_handle=caller_identity["provider_identity_proof_handle"],
        operator_provider_identity_generation=caller_identity["provider_identity_generation"],
        note="retire the exact derived legacy bundle without claiming delivery",
    )

    causes = [
        state.seat_lifecycle_cutover_event_id,
        occupancy.join_event_id,
        occupancy.binding_event_id,
        authority.sent_event_id,
        authority_acknowledgement_event_id,
        replacement.sent_event_id,
        replacement_reconstruction_event_id,
    ]
    assert replacement.acknowledgement_event_id is not None
    causes.append(replacement.acknowledgement_event_id)
    for entry in entries:
        causes.extend(
            (
                state.messages[entry.message_id].sent_event_id,
                entry.materialization_event_id,
            )
        )
    correlation = _correlation(
        correlation_id,
        {
            "recovery_manifest_root": recovery_manifest_root,
            "authority_acknowledgement_event_id": authority_acknowledgement_event_id,
        },
    )
    event = _event(
        EventKind.MESSAGE_MIGRATION_SUPERSESSION,
        recovery.to_dict(),
        actor=actor,
        subject=recovery.transition_id,
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=replacement.assumption,
        fibre=replacement.fibre,
        causation_ids=tuple(dict.fromkeys(causes)),
        body_handle=caller_identity["provider_identity_proof_handle"],
        evidence_handles=(
            capsule_handle,
            author_turn_handle,
            authority.message.body_handle,
        ),
        note=(
            "current v2 Superego atomically retired one author-commissioned derived "
            "historical bundle without claiming delivery"
        ),
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "idempotent": False,
        "receipt": _receipt(stored),
        "replacement_message_id": replacement_message_id,
        "recovery_manifest_root": recovery_manifest_root,
        "manifest": manifest,
        "message_ids": [entry.message_id for entry in entries],
        "statuses": {entry.message_id: store.message_status(entry.message_id) for entry in entries},
        "delivery_claimed": False,
    }


def status(*, message_id: str) -> dict[str, Any]:
    status = _read_store().message_status(message_id)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "message_id": message_id,
        "status": _status_with_dependency_freshness(status),
    }


def expire(
    *,
    message_id: str,
    as_of: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    store = _store()
    state = store.current_state()
    record = state.messages.get(message_id)
    if record is None:
        raise StateTransitionRefused("expiry cites unknown message")
    correlation = _correlation(correlation_id, {"message_id": message_id, "as_of": as_of})
    event = _event(
        EventKind.MESSAGE_EXPIRY,
        MessageExpiry(message_id, as_of).to_dict(),
        actor=SeatRole.SYSTEM,
        subject=f"expiry:{message_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=record.assumption,
        fibre=record.fibre,
        causation_ids=(record.sent_event_id,),
        note="undelivered message expired",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "receipt": _receipt(stored),
        "message_id": message_id,
        "status": store.message_status(message_id),
    }


def request_permission(
    *,
    request_id: str,
    requester_seat_id: str,
    permission: str,
    target: str,
    rationale: str,
    expires_at: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    store = _store()
    state = store.current_state()
    actor = _seat_role(state, requester_seat_id)
    assumption, fibre = _context(state)
    request = PermissionRequest(
        request_id,
        requester_seat_id,
        permission,
        target,
        rationale,
        expires_at,
    )
    correlation = _correlation(correlation_id, {"request_id": request_id})
    event = _event(
        EventKind.PERMISSION_REQUEST,
        request.to_dict(),
        actor=actor,
        subject=f"permission:{request_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=assumption,
        fibre=fibre,
        note="provider permission requested; no authority inferred",
    )
    stored = store.append(event)
    return {"schema_version": BRIDGE_SCHEMA, "receipt": _receipt(stored), "request_id": request_id}


def decide_permission(
    *,
    request_id: str,
    decider_seat_id: str,
    outcome: str,
    reason: str,
    provider: str,
    model: str,
    correlation_id: str = "",
) -> dict[str, Any]:
    store = _store()
    state = store.current_state()
    actor = _seat_role(state, decider_seat_id)
    assumption, fibre = _context(state)
    decision = PermissionDecision(
        request_id,
        decider_seat_id,
        PermissionOutcome(outcome),
        reason,
    )
    request_events = tuple(
        event.event_id
        for event in store.events()
        if event.kind == EventKind.PERMISSION_REQUEST
        and event.payload.get("request_id") == request_id
    )
    correlation = _correlation(correlation_id, {"request_id": request_id, "outcome": outcome})
    event = _event(
        EventKind.PERMISSION_DECISION,
        decision.to_dict(),
        actor=actor,
        subject=f"permission-decision:{request_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=assumption,
        fibre=fibre,
        causation_ids=request_events,
        note=f"permission explicitly {outcome}",
    )
    stored = store.append(event)
    visible = store.provider_snapshot()["permissions"][request_id]
    return {
        "schema_version": BRIDGE_SCHEMA,
        "receipt": _receipt(stored),
        "request_id": request_id,
        "permission": visible,
    }


def register_watcher(
    *,
    watcher_id: str,
    created_by_seat_id: str,
    target_seat_id: str,
    source_kind: str,
    selector: Mapping[str, Any],
    message_type: str,
    one_shot: bool,
    poll_interval_seconds: float,
    expires_at: str,
    provider: str,
    model: str,
    start_cursor: int | None = None,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Register a watcher as typed conceptric topology, not as a shell-loop side channel."""

    store = _store()
    state = store.current_state()
    assumption, fibre = _context(state)
    actor = _seat_role(state, created_by_seat_id)
    _seat_role(state, target_seat_id)
    source = WatchSourceKind(source_kind)
    normalized_selector = dict(selector)
    if source == WatchSourceKind.FILESYSTEM_PATH:
        path = Path(str(normalized_selector.get("path", "")))
        if not path.is_absolute():
            raise StateTransitionRefused("filesystem watcher path must be absolute")
        normalized_selector["path"] = os.fspath(path)
    identity = {
        "creator": created_by_seat_id,
        "target": target_seat_id,
        "source_kind": source.value,
        "selector": normalized_selector,
        "message_type": message_type,
        "one_shot": one_shot,
        "expires_at": expires_at,
    }
    resolved_id = watcher_id.strip() or ("watch:" + chash(identity).removeprefix("sha256:"))
    cursor = state.event_count if start_cursor is None else start_cursor
    registration = WatcherRegistration(
        resolved_id,
        created_by_seat_id,
        target_seat_id,
        source,
        normalized_selector,
        message_type,
        one_shot,
        poll_interval_seconds,
        cursor,
        expires_at,
    )
    existing = state.watchers.get(resolved_id)
    if existing is not None:
        if existing != registration:
            raise StateTransitionRefused("watcher id already names different registration")
        return {
            "schema_version": BRIDGE_SCHEMA,
            "idempotent": True,
            "watcher": state.provider_snapshot()["watchers"][resolved_id],
        }
    seat_causes = tuple(
        event.event_id
        for event in store.events()
        if event.kind == EventKind.SEAT
        and event.payload.get("seat_id") in {created_by_seat_id, target_seat_id}
    )
    correlation = _correlation(correlation_id, {**identity, "watcher_id": resolved_id})
    event = _event(
        EventKind.WATCHER,
        registration.to_dict(),
        actor=actor,
        subject=f"watcher:{resolved_id}",
        provider=provider,
        model=model,
        correlation_id=correlation,
        assumption=assumption,
        fibre=fibre,
        causation_ids=seat_causes,
        note="durable watcher registered in the same conceptric",
    )
    stored = store.append(event)
    return {
        "schema_version": BRIDGE_SCHEMA,
        "idempotent": False,
        "receipt": _receipt(stored),
        "watcher": store.provider_snapshot()["watchers"][resolved_id],
    }


def watch_once(
    *,
    watcher_id: str,
    provider: str = "atlas-watcher",
    model: str = "system-service",
    observed_at: str = "",
) -> dict[str, Any]:
    """Advance one durable subscription cursor and queue any matching handle notification."""

    store = _store()
    state = store.current_state()
    registration = state.watchers.get(watcher_id)
    if registration is None:
        raise StateTransitionRefused("watch poll cites unknown watcher", watcher_id=watcher_id)
    assumption, fibre = state.watcher_contexts[watcher_id]
    if (state.active_assumption, state.active_fibre) != (assumption, fibre):
        return {
            "schema_version": BRIDGE_SCHEMA,
            "watcher_id": watcher_id,
            "blocked": "watcher fibre is not the active fibre; explicit transport required",
        }
    prior = state.watcher_checkpoints.get(watcher_id)
    if prior is not None and registration.one_shot and prior.status == WatchStatus.FIRED:
        return {
            "schema_version": BRIDGE_SCHEMA,
            "watcher_id": watcher_id,
            "idempotent": True,
            "checkpoint": prior.to_dict(),
        }
    when = observed_at.strip() or _now()
    after_cursor = registration.start_cursor if prior is None else prior.result_cursor
    observed_head = state.event_count
    status_value = WatchStatus.ARMED
    matched_handles: tuple[str, ...] = ()
    matched_event_ids: tuple[str, ...] = ()
    if _parsed_time(when) >= _parsed_time(registration.expires_at):
        status_value = WatchStatus.EXPIRED
    elif registration.source_kind == WatchSourceKind.CONCEPTRIC_EVENTS:
        if prior is not None and observed_head <= after_cursor:
            return {
                "schema_version": BRIDGE_SCHEMA,
                "watcher_id": watcher_id,
                "changed": False,
                "checkpoint": prior.to_dict(),
            }
        matched_event_ids = tuple(
            event.event_id
            for position, event in enumerate(store.events(), start=1)
            if after_cursor < position <= observed_head
            and _watch_event_matches(event, registration.selector)
        )
        matched_handles = matched_event_ids
        if matched_handles:
            status_value = WatchStatus.FIRED
    else:
        observation = _filesystem_observation(Path(str(registration.selector["path"])))
        prior_observation = (
            None if prior is None or not prior.matched_handles else prior.matched_handles[-1]
        )
        if observation is not None and observation != prior_observation:
            matched_handles = (observation,)
            status_value = WatchStatus.FIRED
        elif prior is not None:
            return {
                "schema_version": BRIDGE_SCHEMA,
                "watcher_id": watcher_id,
                "changed": False,
                "checkpoint": prior.to_dict(),
            }

    dispatch_message_ids: tuple[str, ...] = ()
    dispatch_event_ids: tuple[str, ...] = ()
    if status_value == WatchStatus.FIRED:
        trigger_body = canonical_json(
            {
                "schema_version": "atlas.watch-trigger.v1",
                "watcher_id": watcher_id,
                "source_kind": registration.source_kind.value,
                "selector": dict(registration.selector),
                "matched_handles": list(matched_handles),
                "after_cursor": after_cursor,
                "result_cursor": observed_head,
                "observed_at": when,
            }
        )
        dispatch = send(
            sender_seat_id=registration.created_by_seat_id,
            recipient_seat_id=registration.target_seat_id,
            message_type=registration.message_type,
            body=trigger_body,
            dependency_roots={
                "watcher": chash(registration.to_dict()),
                **{f"match:{index}": handle for index, handle in enumerate(matched_handles)},
            },
            idempotency_key=(
                "watch-trigger:"
                + chash(
                    {
                        "watcher_id": watcher_id,
                        "after_cursor": after_cursor,
                        "result_cursor": observed_head,
                        "matched_handles": matched_handles,
                    }
                ).removeprefix("sha256:")
            ),
            expires_at=registration.expires_at,
            provider=provider,
            model=model,
            correlation_id=f"watcher:{watcher_id}",
            causation_ids=matched_event_ids,
        )
        dispatch_message_ids = (dispatch["message_id"],)
        dispatch_state = store.current_state().messages[dispatch["message_id"]]
        dispatch_event_ids = (dispatch_state.sent_event_id,)

    # The durable cursor includes the checkpoint row about to be appended.  Otherwise the
    # service would observe its own previous checkpoint as fresh work and churn forever.
    checkpoint_cursor = store.current_state().event_count + 1
    checkpoint = WatchCheckpoint(
        watcher_id,
        after_cursor,
        checkpoint_cursor,
        matched_handles,
        dispatch_message_ids,
        when,
        status_value,
        {
            WatchStatus.ARMED: "no matching event in the observed cursor window",
            WatchStatus.FIRED: "matching handles dispatched; delivery remains unclaimed",
            WatchStatus.EXPIRED: "watcher deadline elapsed without inferred delivery",
            WatchStatus.ERROR: "watcher error",
        }[status_value],
    )
    current = store.current_state()
    actor = _seat_role(current, registration.created_by_seat_id)
    event = _event(
        EventKind.WATCH_CHECKPOINT,
        checkpoint.to_dict(),
        actor=actor,
        subject=f"watch-checkpoint:{watcher_id}:{checkpoint_cursor}",
        provider=provider,
        model=model,
        correlation_id=f"watcher:{watcher_id}",
        assumption=assumption,
        fibre=fibre,
        causation_ids=(*matched_event_ids, *dispatch_event_ids),
        note=checkpoint.note,
    )
    try:
        stored = store.append(event)
    except StateTransitionRefused:
        raced = store.current_state().watcher_checkpoints.get(watcher_id)
        if raced is None or raced.result_cursor < checkpoint_cursor:
            raise
        return {
            "schema_version": BRIDGE_SCHEMA,
            "watcher_id": watcher_id,
            "idempotent": True,
            "checkpoint": raced.to_dict(),
        }
    return {
        "schema_version": BRIDGE_SCHEMA,
        "watcher_id": watcher_id,
        "receipt": _receipt(stored),
        "checkpoint": checkpoint.to_dict(),
        "dispatch_message_ids": list(dispatch_message_ids),
        "delivery_claimed": False,
    }


def watch_all_once(
    *, provider: str = "atlas-watcher", model: str = "system-service"
) -> dict[str, Any]:
    watcher_ids = tuple(sorted(_store().current_state().watchers))
    results: list[dict[str, Any]] = []
    for watcher_id in watcher_ids:
        try:
            results.append(watch_once(watcher_id=watcher_id, provider=provider, model=model))
        except (StateTransitionRefused, OSError, ValueError) as exc:
            results.append({"watcher_id": watcher_id, "error": str(exc)})
    return {
        "schema_version": BRIDGE_SCHEMA,
        "watcher_count": len(watcher_ids),
        "results": results,
    }


__all__ = [
    "BRIDGE_SCHEMA",
    "acknowledge",
    "atlas_object",
    "authority_epoch",
    "blueprint_custody_projection",
    "authorize_region_publication",
    "decide_permission",
    "development_review_frontier",
    "expire",
    "lifecycle",
    "mail_obligations",
    "inspect_authority_epoch",
    "prepare_authority_epoch",
    "prepare_region_publication",
    "prepare_seat_mail_projection",
    "provider_seat_binding",
    "pull",
    "recover_legacy_message_bundle",
    "recover_region_publication",
    "reconstruct",
    "request_permission",
    "region_publication",
    "finalize_region_publication",
    "seat_join",
    "seat_mail_observation",
    "seat_transition",
    "select_context",
    "send",
    "sign_region_publication",
    "snapshot",
    "status",
    "store_root",
    "transport_context",
    "verify_atlas_object_current_root",
    "register_watcher",
    "watch_all_once",
    "watch_once",
]
