from __future__ import annotations

import fcntl
import json
import shutil
import sqlite3
import subprocess
import threading
from pathlib import Path

import pytest

from atlas.errors import (
    BlobHashMismatch,
    BlobMissing,
    HistoryChainMismatch,
    StoreError,
    StoreLockTimeout,
)
from atlas.history import (
    AtlasEvent,
    ConceptricObject,
    EventKind,
    LifecycleAction,
    LifecyclePhase,
    LifecycleTransition,
    ProducerRef,
    Residual,
    ResidualStatus,
    SeatRole,
    SourceRef,
    Validity,
)
from atlas.ids import canonical_json, chash
from atlas.runtime import collect_runtime_receipt
from atlas.state import CONTROL_AXIS_CONTRACT, ConceptricState
from atlas.store import (
    AUTHORITY_AFFECTING_EVENT_KINDS,
    CONCEPTRIC_DB_SCHEMA,
    DEFAULT_EVENT_HIVE_REF,
    DEVELOPMENT_REVIEW_PROJECTION_SCHEMA,
    GENESIS_DIGEST,
    GRAPH_PROJECTION_SCHEMA,
    LEGACY_CONCEPTRIC_DB_SCHEMA,
    CompressedHive,
    ConceptricStore,
    StoredEvent,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = SourceRef("store-projection-test", "sha256:" + ("a" * 64), "test:store")
RESIDUAL = Residual(
    ResidualStatus.WITHIN_BOUND, 0.0, 0.0, "structural-violations", "test proof"
)
RUNTIME = collect_runtime_receipt(ROOT, observed_at="2026-08-24T12:00:00Z")


def test_read_portable_authority_adoption_absent_and_malformed_are_read_only(tmp_path):
    from atlas.store import PORTABLE_AUTHORITY_ADOPTION_META_KEY
    store = ConceptricStore(tmp_path, expected_store_role="fixture")
    ledger = tmp_path / "conceptric.sqlite3"
    before = ledger.read_bytes()
    assert ConceptricStore.read_portable_authority_adoption(
        tmp_path, expected_store_role="fixture") is None
    assert ledger.read_bytes() == before
    with store._connect() as connection:
        connection.execute("INSERT INTO meta(key, value) VALUES (?, ?)",
                           (PORTABLE_AUTHORITY_ADOPTION_META_KEY, "not-json"))
        connection.commit()
    before = ledger.read_bytes()
    with pytest.raises(StoreError, match="receipt is malformed"):
        ConceptricStore.read_portable_authority_adoption(tmp_path, expected_store_role="fixture")
    assert ledger.read_bytes() == before


def test_seal_portable_authority_adoption_refuses_absent_receipt_without_write(tmp_path):
    ConceptricStore(tmp_path, expected_store_role="fixture")
    ledger = tmp_path / "conceptric.sqlite3"
    before = ledger.read_bytes()
    with pytest.raises(StoreError, match="adoption is absent"):
        ConceptricStore.seal_portable_authority_adoption(
            tmp_path, expected_store_role="fixture",
            expected_source_snapshot_id="sha256:" + "1" * 64,
            expected_checkpoint_digest="sha256:" + "2" * 64,
            expected_grant_root="sha256:" + "3" * 64,
            target_canonical_root=tmp_path)
    assert ledger.read_bytes() == before


def test_caller_authority_files_rebind_append_and_refuse_disk_drift(tmp_path, monkeypatch):
    import atlas.store as module

    container = tmp_path / "container"
    for relative in module._AUTHORITY_CONTEXT_RELATIVE_PATHS:
        target = container / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(module._AUTHORITY_CONTEXT_REPOSITORY / relative, target)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.setattr(module, "_AUTHORITY_CONTEXT_REPOSITORY", container)
    caller = tmp_path / "consumer.py"
    caller.write_text("generation = 1\n")
    extra = (caller,)
    root = tmp_path / "store"
    base = ConceptricStore(root)
    base_context = base._authority_context
    evidence = ConceptricStore.authority_context_evidence(root, extra_authority_files=extra)
    assert evidence["manifest"]["files"]["../consumer.py"] == sha256_file(caller)
    assert "../consumer.py" in evidence["dirty"]["manifest_paths"]
    assert ConceptricStore.authority_context_manifest(root) == base_context
    assert evidence["roots"]["implementation_digest"] != base_context["implementation_digest"]
    deep = ConceptricStore.verify_authority_checkpoint_deep(root, extra_authority_files=extra)
    ConceptricStore.prepare_authority_checkpoint(
        root, expected_predecessor=deep["verified_predecessor"],
        authority_context=evidence["roots"], extra_authority_files=extra,
    )
    store = ConceptricStore(root, extra_authority_files=extra)
    store.append(_wake())
    assert ConceptricStore.read_authority_checkpoint(
        root, extra_authority_files=extra,
    )["status"] == "CURRENT"
    assert ConceptricStore.verify_authority_checkpoint_deep(
        root, extra_authority_files=extra,
    )["fast_deep_equal"]
    before = ConceptricStore.read_drift_token(root)
    caller.write_text("generation = 2\n")
    with pytest.raises(StoreError, match="loaded code differs from disk"):
        ConceptricStore.read_authority_checkpoint(root, extra_authority_files=extra)
    with pytest.raises(StoreError, match="loaded code differs from disk"):
        store.append(_object_event("object:after-drift", kind="test", content="sha256:" + "a" * 64))
    assert ConceptricStore.read_drift_token(root) == before
    # An unrelated declaration must never widen the default container authority.
    assert ConceptricStore.authority_context_manifest(root) == base_context


def _wake() -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at="2026-08-24T12:00:00Z",
        kind=EventKind.LIFECYCLE,
        producer=SeatRole.SYSTEM,
        actor=SeatRole.SYSTEM,
        subject="lifecycle:projection-test",
        assumption=None,
        fibre=None,
        correlation_id="projection-test",
        causation_ids=(),
        provenance=(SOURCE,),
        residual=RESIDUAL,
        runtime=RUNTIME,
        producer_ref=ProducerRef("pytest", "system", "test"),
        validity=Validity.VALID,
        payload=LifecycleTransition(
            LifecycleAction.COLD_WAKE,
            LifecyclePhase.SLEEPING,
            LifecyclePhase.AWAKE,
            "cold:projection-test",
        ).to_dict(),
    )


def _object_event(object_id: str, *, kind: str, content: str) -> AtlasEvent:
    item = ConceptricObject(
        object_id=object_id,
        kind=kind,
        content_handle=content,
        assumption=None,
        fibre=None,
        grade_contract_id=CONTROL_AXIS_CONTRACT.contract_id,
        grade_coordinate="content",
        provenance=(SOURCE,),
        attributes={"test": True},
    )
    return AtlasEvent.create(
        occurred_at="2026-08-24T12:00:01Z",
        kind=EventKind.OBJECT,
        producer=SeatRole.SYSTEM,
        actor=SeatRole.AUTHOR,
        subject=object_id,
        assumption=None,
        fibre=None,
        correlation_id=f"projection-object:{object_id}",
        causation_ids=(),
        provenance=(SOURCE,),
        residual=RESIDUAL,
        runtime=RUNTIME,
        producer_ref=ProducerRef("pytest", "system", "test"),
        validity=Validity.VALID,
        payload=item.to_dict(),
    )


def _foreign_wake() -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at="2026-08-24T12:00:00Z",
        kind=EventKind.LIFECYCLE,
        producer=SeatRole.SYSTEM,
        actor=SeatRole.SYSTEM,
        subject="lifecycle:foreign-projection-test",
        assumption=None,
        fibre=None,
        correlation_id="foreign-projection-test",
        causation_ids=(),
        provenance=(SOURCE,),
        residual=RESIDUAL,
        runtime=RUNTIME,
        producer_ref=ProducerRef("pytest", "system", "test"),
        validity=Validity.VALID,
        payload=LifecycleTransition(
            LifecycleAction.COLD_WAKE,
            LifecyclePhase.SLEEPING,
            LifecyclePhase.AWAKE,
            "cold:foreign-projection-test",
        ).to_dict(),
    )


def _sew() -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at="2026-08-24T12:01:00Z",
        kind=EventKind.LIFECYCLE,
        producer=SeatRole.SYSTEM,
        actor=SeatRole.SYSTEM,
        subject="lifecycle:projection-test-sew",
        assumption=None,
        fibre=None,
        correlation_id="projection-test-sew",
        causation_ids=(),
        provenance=(SOURCE,),
        residual=RESIDUAL,
        runtime=RUNTIME,
        producer_ref=ProducerRef("pytest", "system", "test"),
        validity=Validity.VALID,
        payload=LifecycleTransition(
            LifecycleAction.SEW_UP,
            LifecyclePhase.AWAKE,
            LifecyclePhase.SEWING_UP,
            "sew:projection-test",
        ).to_dict(),
    )


def _unrelated(index: int) -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at="2026-08-24T12:02:00Z",
        kind=EventKind.OBSERVATION,
        producer=SeatRole.SYSTEM,
        actor=SeatRole.SYSTEM,
        subject=f"sensorium:authority-suffix:{index}",
        assumption=None,
        fibre=None,
        correlation_id="authority-suffix-volume",
        causation_ids=(),
        provenance=(SOURCE,),
        residual=RESIDUAL,
        runtime=RUNTIME,
        producer_ref=ProducerRef("pytest", "system", "test"),
        validity=Validity.REFUSED,
        payload={
            "schema_version": "test.authority-neutral-observation/1",
            "index": index,
            "authority_effect": "none",
        },
    )


def _sleep() -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at="2026-08-24T12:02:00Z",
        kind=EventKind.LIFECYCLE,
        producer=SeatRole.SYSTEM,
        actor=SeatRole.SYSTEM,
        subject="lifecycle:projection-test-sleep",
        assumption=None,
        fibre=None,
        correlation_id="projection-test-sleep",
        causation_ids=(),
        provenance=(SOURCE,),
        residual=RESIDUAL,
        runtime=RUNTIME,
        producer_ref=ProducerRef("pytest", "system", "test"),
        validity=Validity.VALID,
        payload=LifecycleTransition(
            LifecycleAction.SLEEP,
            LifecyclePhase.SEWING_UP,
            LifecyclePhase.SLEEPING,
            "sleep:projection-test",
        ).to_dict(),
    )


def test_read_only_store_uses_query_only_and_cannot_mutate_authority(tmp_path: Path) -> None:
    root = tmp_path / "store"
    writer = ConceptricStore(root)
    writer.append(_wake())
    # Establish a writer-owned stable byte boundary.  Otherwise SQLite may consolidate the
    # writer's committed WAL while opening a later read-only view, which is storage housekeeping
    # rather than a read-capability mutation but makes the byte assertion scheduler-dependent.
    with writer._connect() as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    watched = [p for p in (writer.path, writer.projection_path,
                           writer.path.with_name(writer.path.name + "-wal")) if p.is_file()]
    before = {p: p.read_bytes() for p in watched}

    reader = ConceptricStore(root, read_only=True)
    with reader._connect() as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE forbidden(value TEXT)")
    assert reader.replay() == writer.replay()
    with pytest.raises(StoreError, match="refuses append"):
        reader.append(_sew())
    with pytest.raises(StoreError, match="refuses migration"):
        reader.migrate_hived(store_role="test-fixture")
    assert {p: p.read_bytes() for p in watched} == before


def test_read_only_fresh_clone_does_not_create_a_coordination_lock(tmp_path: Path) -> None:
    root = tmp_path / "store"
    writer = ConceptricStore(root)
    writer.append(_wake())
    writer.lock_path.unlink()

    reader = ConceptricStore(root, read_only=True)
    assert reader.replay().event_count == 1
    assert not writer.lock_path.exists()


def test_store_lock_wait_is_bounded(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path / "store")
    with store.lock_path.open("a+b") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        try:
            with pytest.raises(StoreLockTimeout, match="timed out") as exc:
                with store._locked(shared=True, timeout=0.02):
                    pass
            assert exc.value.reason == "store-lock-timeout"
        finally:
            fcntl.flock(held.fileno(), fcntl.LOCK_UN)


def test_body_oserror_is_not_mislabeled_as_a_lock_failure(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path / "store")
    with pytest.raises(OSError, match="disk full"):
        with store._locked():
            raise OSError("disk full")


def _legacy_v1_store(root: Path) -> ConceptricStore:
    root.mkdir(parents=True)
    stored = StoredEvent.create(1, GENESIS_DIGEST, _wake())
    with sqlite3.connect(root / "conceptric.sqlite3") as connection:
        connection.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE events (
                sequence INTEGER PRIMARY KEY,
                previous_digest TEXT NOT NULL,
                record_digest TEXT NOT NULL UNIQUE,
                event_id TEXT NOT NULL UNIQUE,
                event_kind TEXT NOT NULL,
                assumption TEXT,
                fibre TEXT,
                event_json TEXT NOT NULL
            );
            CREATE TABLE objects (
                object_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content_handle TEXT NOT NULL,
                assumption TEXT,
                fibre TEXT,
                grade_contract_id TEXT NOT NULL,
                grade_coordinate_json TEXT NOT NULL,
                declared_event_id TEXT NOT NULL,
                object_json TEXT NOT NULL,
                FOREIGN KEY(declared_event_id) REFERENCES events(event_id)
            ) WITHOUT ROWID;
            CREATE TABLE edges (
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
                FOREIGN KEY(target_object_id) REFERENCES objects(object_id),
                FOREIGN KEY(declared_event_id) REFERENCES events(event_id)
            ) WITHOUT ROWID;
            """
        )
        connection.executemany(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            (
                ("schema_version", LEGACY_CONCEPTRIC_DB_SCHEMA),
                ("graph_projection_schema", "atlas.conceptric-graph-projection/fixture-stale"),
                ("legacy_jsonl_sha256", "sha256:" + ("b" * 64)),
            ),
        )
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
                stored.event.event_id,
                stored.event.kind.value,
                stored.event.assumption,
                stored.event.fibre,
                canonical_json(stored.event.to_dict()),
            ),
        )
    return ConceptricStore(root)


def test_writer_rebuilds_current_head_projection_poison_automatically(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path / "conceptric")
    stored = store.append(_wake())
    with store._connect() as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    ledger_before = store.path.read_bytes()
    hives_before = {
        path.relative_to(store.hive_root): path.read_bytes()
        for path in store.hive_root.rglob("*")
        if path.is_file()
    }
    with sqlite3.connect(store.projection_path) as connection:
        connection.execute(
            "UPDATE objects SET object_json = ? WHERE object_id = "
            "(SELECT object_id FROM objects LIMIT 1)",
            ('{"tampered":true}',),
        )

    state = store.replay()

    assert state.head_event_id == stored.event.event_id
    assert store.path.read_bytes() == ledger_before
    assert {
        path.relative_to(store.hive_root): path.read_bytes()
        for path in store.hive_root.rglob("*")
        if path.is_file()
    } == hives_before
    with sqlite3.connect(store.projection_path) as connection:
        connection.row_factory = sqlite3.Row
        store._verify_graph_projection(connection, state)
    assert tuple(store.root.glob(".conceptric.index.sqlite3.retired-*")) == ()


def test_repeated_projection_rebuilds_do_not_retain_full_disposable_databases(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bounded-projection-retirement"
    store = ConceptricStore(root)
    store.append(_wake())

    for generation in range(3):
        with sqlite3.connect(store.projection_path) as connection:
            connection.execute(
                "UPDATE meta SET value = ? WHERE key = 'graph_projection_schema'",
                (f"atlas.conceptric-graph-projection/stale-{generation}",),
            )
        store = ConceptricStore(root)

    assert store.replay().event_count == 1
    assert tuple(root.glob(".conceptric.index.sqlite3.retired-*")) == ()


def test_new_writer_rebuilds_non_sqlite_projection_bytes_automatically(tmp_path: Path) -> None:
    root = tmp_path / "conceptric"
    store = ConceptricStore(root)
    stored = store.append(_wake())
    ledger_before = store.path.read_bytes()
    store.projection_path.write_bytes(b"not a sqlite database")

    rebuilt = ConceptricStore(root)

    assert rebuilt.replay().head_event_id == stored.event.event_id
    assert store.path.read_bytes() == ledger_before


def test_new_writer_quarantines_directory_at_projection_path(tmp_path: Path) -> None:
    root = tmp_path / "conceptric"
    store = ConceptricStore(root)
    stored = store.append(_wake())
    store.projection_path.unlink()
    store.projection_path.mkdir()
    (store.projection_path / "planted.txt").write_text("not disposable evidence")

    rebuilt = ConceptricStore(root)

    assert rebuilt.replay().head_event_id == stored.event.event_id
    assert rebuilt.projection_path.is_file()
    residues = tuple(root.glob(".conceptric.index.sqlite3.retired-*"))
    assert len(residues) == 1
    assert (residues[0] / "planted.txt").read_text() == "not disposable evidence"


def test_append_repairs_directory_at_projection_wal_without_ambiguous_failure(
    tmp_path: Path,
) -> None:
    root = tmp_path / "conceptric"
    store = ConceptricStore(root)
    store.append(_wake())
    wal = store.projection_path.with_name(store.projection_path.name + "-wal")
    wal.unlink(missing_ok=True)
    wal.mkdir()
    (wal / "planted.txt").write_text("sidecar obstruction")

    stored = store.append(_sew())

    assert store.replay().head_event_id == stored.event.event_id
    residues = tuple(root.glob(".conceptric.index.sqlite3-wal.retired-*"))
    assert len(residues) == 1
    assert (residues[0] / "planted.txt").read_text() == "sidecar obstruction"


def test_read_only_face_reconstructs_projection_poison_without_rewriting_it(
    tmp_path: Path,
) -> None:
    root = tmp_path / "conceptric"
    store = ConceptricStore(root)
    stored = store.append(_wake())
    with sqlite3.connect(store.projection_path) as connection:
        connection.execute(
            "UPDATE objects SET object_json = ? WHERE object_id = "
            "(SELECT object_id FROM objects LIMIT 1)",
            ('{"tampered":true}',),
        )
    poison = store.projection_path.read_bytes()

    state = ConceptricStore(root, read_only=True).replay()

    assert state.head_event_id == stored.event.event_id
    assert store.projection_path.read_bytes() == poison


def test_projection_schema_change_rebuilds_only_disposable_graph(tmp_path: Path) -> None:
    root = tmp_path / "conceptric"
    store = ConceptricStore(root)
    stored = store.append(_wake())
    with sqlite3.connect(store.projection_path) as connection:
        connection.execute("DELETE FROM edges")
        connection.execute("DELETE FROM objects")
        connection.execute(
            "UPDATE meta SET value = ? WHERE key = 'graph_projection_schema'",
            ("atlas.conceptric-graph-projection/old",),
        )
    rebuilt = ConceptricStore(root)
    state = rebuilt.replay()
    assert state.head_event_id == stored.event.event_id
    assert state.graph_objects
    with sqlite3.connect(store.projection_path) as connection:
        version = connection.execute(
            "SELECT value FROM meta WHERE key = 'graph_projection_schema'"
        ).fetchone()[0]
    assert version == GRAPH_PROJECTION_SCHEMA


def test_older_graph_writer_cannot_false_stamp_review_frontier_current(
    tmp_path: Path,
) -> None:
    """Graph schema stays rolling-compatible; review currentness has its own head."""

    root = tmp_path / "conceptric"
    store = ConceptricStore(root)
    stored = store.append(_wake())
    with sqlite3.connect(store.projection_path) as connection:
        graph_schema = connection.execute(
            "SELECT value FROM meta WHERE key = 'graph_projection_schema'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE meta SET value = ? WHERE key = 'development_review_head_digest'",
            (GENESIS_DIGEST,),
        )

    assert graph_schema == GRAPH_PROJECTION_SCHEMA
    with pytest.raises(HistoryChainMismatch, match="frontier is stale") as caught:
        ConceptricStore.read_development_review_frontier(root)
    assert caught.value.reason == "store-history-chain-mismatch"

    rebuilt = ConceptricStore(root)
    frontier = ConceptricStore.read_development_review_frontier(root)
    assert rebuilt.current_state().head_event_id == stored.event.event_id
    assert frontier["head_event_id"] == stored.event.event_id
    with sqlite3.connect(store.projection_path) as connection:
        meta = dict(
            connection.execute(
                "SELECT key, value FROM meta WHERE key IN "
                "('graph_projection_schema', 'development_review_projection_schema')"
            )
        )
    assert meta == {
        "graph_projection_schema": GRAPH_PROJECTION_SCHEMA,
        "development_review_projection_schema": DEVELOPMENT_REVIEW_PROJECTION_SCHEMA,
    }


def test_normalized_edges_have_enforced_resolvable_endpoints(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path / "conceptric")
    stored = store.append(_wake())
    with sqlite3.connect(store.projection_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO edges(
                    edge_id, relation, source_object_id, target_object_id, direction,
                    assumption, fibre, operator, generation_handle, declared_event_id,
                    edge_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "edge:dangling",
                    "cannot-resolve",
                    "object:missing-source",
                    "object:missing-target",
                    "outward",
                    None,
                    None,
                    "adversarial-insert",
                    stored.event.event_id,
                    stored.event.event_id,
                    "{}",
                ),
            )


def test_new_store_uses_compact_ledger_hives_and_separate_projection(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path / "conceptric")
    stored = store.append(_wake())

    with sqlite3.connect(store.path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(events)")
        }
        row = connection.execute(
            "SELECT event_handle, record_digest FROM events WHERE sequence = 1"
        ).fetchone()
        schema = connection.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()[0]
    assert schema == CONCEPTRIC_DB_SCHEMA
    assert "event_handle" in columns
    assert "event_json" not in columns
    assert row[1] == stored.record_digest
    assert store.hive.get(row[0]) == canonical_json(stored.event.to_dict()).encode()
    assert store.projection_path.is_file()
    with sqlite3.connect(store.path) as connection:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='objects'"
        ).fetchone() is None


def test_ledger_reopens_an_external_hive_without_process_local_configuration(tmp_path: Path) -> None:
    root = tmp_path / "conceptric"
    external = tmp_path / "external-custody" / "events"
    store = ConceptricStore(root, hive_root=external)
    store.append(_wake())
    expected = store.replay()

    cold = ConceptricStore(root)

    assert cold.hive_root == external.resolve()
    assert cold.replay() == expected
    with pytest.raises(StoreError, match="disagrees with the ledger"):
        ConceptricStore(root, hive_root=tmp_path / "wrong-custody")


def test_missing_projection_is_rebuilt_but_missing_event_hive_refuses(tmp_path: Path) -> None:
    root = tmp_path / "conceptric"
    store = ConceptricStore(root)
    store.append(_wake())
    expected = store.replay()

    store.projection_path.unlink()
    assert ConceptricStore(root).replay() == expected

    with sqlite3.connect(store.path) as connection:
        handle = connection.execute(
            "SELECT event_handle FROM events WHERE sequence = 1"
        ).fetchone()[0]
    store.hive.key_path(handle).unlink()
    with pytest.raises(BlobMissing) as exc:
        ConceptricStore(root)
    assert exc.value.reason == "store-blob-missing"


def test_fresh_clone_read_only_reconstructs_v2_without_shipping_projection(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    store = ConceptricStore(source)
    store.append_many((_wake(), _sew()))
    store.seal_custody(store_role="test-fixture")
    expected = store.replay()

    clone = tmp_path / "clone"
    clone.mkdir()
    shutil.copy2(store.path, clone / store.path.name)
    shutil.copytree(store.hive_root, clone / DEFAULT_EVENT_HIVE_REF)

    reader = ConceptricStore(clone, read_only=True)
    assert reader.replay() == expected
    assert not reader.projection_path.exists()


def test_read_only_replay_reconstructs_stale_projection_in_memory_without_repairing_disk(
    tmp_path: Path,
) -> None:
    root = tmp_path / "stale-index"
    store = ConceptricStore(root)
    store.append(_wake())
    with sqlite3.connect(store.projection_path) as connection:
        connection.execute(
            "UPDATE meta SET value = ? WHERE key = 'authoritative_head_digest'",
            (GENESIS_DIGEST,),
        )
    before = store.projection_path.read_bytes()

    reader = ConceptricStore(root, read_only=True)
    assert reader.replay().head_event_id == _wake().event_id
    assert store.projection_path.read_bytes() == before


def test_append_adds_one_chunk_without_rewriting_prior_hive_content(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path / "bounded-append")
    store.append(_wake())
    with sqlite3.connect(store.path) as connection:
        first_handle = connection.execute(
            "SELECT event_handle FROM events WHERE sequence = 1"
        ).fetchone()[0]
    first_path = store.hive.key_path(first_handle)
    first_stat = first_path.stat()
    ledger_size = store.path.stat().st_size

    store.append(_sew())

    assert first_path.stat().st_mtime_ns == first_stat.st_mtime_ns
    assert first_path.stat().st_size == first_stat.st_size
    assert len(list(store.hive_root.rglob("*.zlib"))) == 2
    assert store.path.stat().st_size - ledger_size <= 128 * 1024


def test_append_folds_onto_verified_head_without_reading_historical_hives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConceptricStore(tmp_path / "delta-append")
    store.append(_wake())
    original_get = CompressedHive.get
    reads: list[str] = []

    def counted_get(self, key):
        reads.append(key)
        return original_get(self, key)

    monkeypatch.setattr(CompressedHive, "get", counted_get)
    stored = store.append(_sew())
    assert reads == [], "a new append must not inflate any historical event chunk"

    retried = store.append(_wake())
    assert retried.event.event_id == _wake().event_id
    assert len(reads) == 1, "an idempotent retry verifies only the event it returns"
    with sqlite3.connect(store.path) as connection:
        head = connection.execute(
            "SELECT value FROM meta WHERE key = 'authoritative_head_digest'"
        ).fetchone()[0]
    assert head == stored.record_digest


def test_external_tip_drift_forces_refresh_before_delta_append(tmp_path: Path) -> None:
    root = tmp_path / "two-writers"
    first = ConceptricStore(root)
    stale = ConceptricStore(root)
    first.append(_wake())

    stale.append(_sew())

    cold = ConceptricStore(root)
    assert [event.event_id for event in cold.events()] == [_wake().event_id, _sew().event_id]
    assert cold.replay().head_event_id == _sew().event_id


def test_external_tip_drift_reads_only_the_unseen_verified_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "two-writers-delta"
    first = ConceptricStore(root)
    first.append(_wake())
    stale = ConceptricStore(root)
    first.append(_sew())
    with sqlite3.connect(first.path) as connection:
        external_handle = connection.execute(
            "SELECT event_handle FROM events WHERE sequence = 2"
        ).fetchone()[0]
    original_get = CompressedHive.get
    reads: list[str] = []

    def counted_get(self, key):
        reads.append(key)
        return original_get(self, key)

    monkeypatch.setattr(CompressedHive, "get", counted_get)
    stored = stale.append(_sleep())

    assert reads == [external_handle]
    assert stored.sequence == 3
    assert stale.replay().head_event_id == _sleep().event_id


def test_external_tip_drift_falls_back_to_full_replay_at_a_projection_crash_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "two-writers-crash-seam"
    first = ConceptricStore(root)
    first.append(_wake())
    stale = ConceptricStore(root)
    first.append(_sew())
    with sqlite3.connect(first.projection_path) as connection:
        connection.execute(
            "UPDATE meta SET value = ? WHERE key = 'authoritative_head_digest'",
            (GENESIS_DIGEST,),
        )
    original_full_replay = stale._read_v2_rows_from
    full_replays = 0

    def counted_full_replay(connection):
        nonlocal full_replays
        full_replays += 1
        return original_full_replay(connection)

    monkeypatch.setattr(stale, "_read_v2_rows_from", counted_full_replay)
    state = stale.current_state()

    assert state.head_event_id == _sew().event_id
    assert full_replays == 1
    assert stale._verified_sequence == 2
    assert stale._verified_head_digest == ConceptricStore.read_drift_token(root)[
        "head_record_digest"
    ]


def test_persistent_read_only_state_folds_only_the_suffix_and_never_repairs_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "read-only-delta"
    writer = ConceptricStore(root)
    writer.append(_wake())
    reader = ConceptricStore(root, read_only=True)
    assert reader.current_state().head_event_id == _wake().event_id
    writer.append(_sew())
    with sqlite3.connect(writer.path) as connection:
        external_handle = connection.execute(
            "SELECT event_handle FROM events WHERE sequence = 2"
        ).fetchone()[0]
    with sqlite3.connect(writer.projection_path) as connection:
        connection.execute(
            "UPDATE meta SET value = ? WHERE key = 'authoritative_head_digest'",
            (GENESIS_DIGEST,),
        )
    poison = writer.projection_path.read_bytes()
    original_get = CompressedHive.get
    reads: list[str] = []

    def counted_get(self, key):
        reads.append(key)
        return original_get(self, key)

    monkeypatch.setattr(CompressedHive, "get", counted_get)
    state = reader.current_state()

    assert state.head_event_id == _sew().event_id
    assert reads == [external_handle]
    assert writer.projection_path.read_bytes() == poison


def test_two_cold_readers_share_one_atomic_verified_head_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "concurrent-cold-current-state"
    reader = ConceptricStore(root)
    writer = ConceptricStore(root)
    stored = writer.append(_wake())
    fold_entered = threading.Barrier(2)
    release_fold = threading.Barrier(2)
    second_finished = threading.Event()
    failures: list[BaseException] = []
    results: list[ConceptricState] = []
    fold_calls = 0
    original_fold = reader._fold

    def paused_fold(rows):
        nonlocal fold_calls
        fold_calls += 1
        fold_entered.wait(timeout=5)
        release_fold.wait(timeout=5)
        return original_fold(rows)

    monkeypatch.setattr(reader, "_fold", paused_fold)
    monkeypatch.setattr(
        reader, "_projection_receipt_matches", lambda *, expected_head: False
    )
    monkeypatch.setattr(reader, "_ensure_projection", lambda rows: None)

    def read(*, finished: threading.Event | None = None) -> None:
        try:
            results.append(reader.current_state())
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)
        finally:
            if finished is not None:
                finished.set()

    first = threading.Thread(target=read)
    first.start()
    fold_entered.wait(timeout=5)
    second = threading.Thread(target=read, kwargs={"finished": second_finished})
    second.start()
    assert not second_finished.wait(timeout=0.1), (
        "a second cold reader entered while the verified head triple was being refreshed"
    )
    release_fold.wait(timeout=5)
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive() and not second.is_alive()
    assert failures == []
    assert len(results) == 2
    assert results[0] is results[1]
    assert fold_calls == 1
    assert results[0].event_count == 1
    assert results[0].head_event_id == stored.event.event_id
    assert reader._verified_sequence == 1
    assert reader._verified_head_digest == stored.record_digest


def test_replay_holds_one_read_snapshot_across_ledger_and_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "read-write-seam"
    reader = ConceptricStore(root)
    reader.append(_wake())
    writer = ConceptricStore(root)
    reader_entered_projection = threading.Event()
    release_reader = threading.Event()
    writer_finished = threading.Event()
    failures: list[BaseException] = []
    verify = reader._verify_graph_projection

    def paused_verify(connection, state, rows=None):
        reader_entered_projection.set()
        if not release_reader.wait(timeout=5):
            raise AssertionError("test did not release the paused replay")
        return verify(connection, state, rows)

    monkeypatch.setattr(reader, "_verify_graph_projection", paused_verify)

    def read() -> None:
        try:
            reader.replay()
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    def write() -> None:
        try:
            writer.append(_sew())
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)
        finally:
            writer_finished.set()

    read_thread = threading.Thread(target=read)
    read_thread.start()
    assert reader_entered_projection.wait(timeout=5)
    write_thread = threading.Thread(target=write)
    write_thread.start()
    assert not writer_finished.wait(timeout=0.1), (
        "writer crossed the ledger/projection seam while a replay held its read snapshot"
    )
    release_reader.set()
    read_thread.join(timeout=5)
    write_thread.join(timeout=5)

    assert not read_thread.is_alive() and not write_thread.is_alive()
    assert failures == []
    assert ConceptricStore(root).replay().head_event_id == _sew().event_id


def test_drift_token_reads_only_the_compact_tip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "drift-token"
    store = ConceptricStore(root)
    assert ConceptricStore.read_drift_token(root) == {
        "schema_version": "atlas.conceptric-drift-token/1",
        "cursor": 0,
        "head_event_id": None,
        "head_record_digest": GENESIS_DIGEST,
    }
    stored = store.append(_wake())

    def refuse_hive_read(*_args, **_kwargs):
        raise AssertionError("a drift token must not descend into an event hive")

    monkeypatch.setattr(CompressedHive, "get", refuse_hive_read)
    assert ConceptricStore.read_drift_token(root) == {
        "schema_version": "atlas.conceptric-drift-token/1",
        "cursor": 1,
        "head_event_id": stored.event.event_id,
        "head_record_digest": stored.record_digest,
    }


def test_hive_reachability_is_head_bound_and_names_orphans_without_deleting(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path / "reachability")
    stored = store.append(_wake())
    clean = store.hive_reachability()

    assert clean["status"] == "exact"
    assert clean["ledger_head_digest"] == stored.record_digest
    assert clean["event_count"] == clean["unique_marked_chunks"] == 1
    assert clean["orphan_handles"] == ()

    orphan = store.hive.put(b"unreachable candidate bytes")
    marked = store.hive_reachability()
    assert marked["status"] == "exact"
    assert marked["orphan_handles"] == (orphan,)
    assert store.hive.has(orphan)

    malformed = store.hive_root / "loose-unreceipted.tmp"
    malformed.write_bytes(b"not a hive chunk")
    residue = store.hive_reachability()
    assert residue["status"] == "residue"
    assert residue["invalid_paths"] == (malformed.name,)


def test_custody_seal_binds_ledger_hives_receipts_and_zero_orphans(tmp_path: Path) -> None:
    root = tmp_path / "sealed"
    store = ConceptricStore(root)
    stored = store.append(_wake())

    receipt = store.seal_custody(store_role="test-fixture")

    assert receipt["event_count"] == 1
    assert receipt["head_digest"] == stored.record_digest
    assert receipt["reachability"]["orphan_handles"] == []
    assert receipt["migration"] == {"present": False}
    assert ConceptricStore(root, read_only=True).verify_custody() == receipt
    with pytest.raises(StoreError, match="refuses to relabel"):
        store.seal_custody(store_role="different-fixture")


def test_custody_seal_refuses_an_empty_authority_without_minting_identity(
    tmp_path: Path,
) -> None:
    store = ConceptricStore(tmp_path / "empty-seal")

    with pytest.raises(StoreError, match="empty authority"):
        store.seal_custody(store_role="test-fixture")

    assert not store.custody_receipt_path.exists()
    with sqlite3.connect(store.path) as connection:
        assert connection.execute(
            "SELECT value FROM meta WHERE key = 'store_identity_json'"
        ).fetchone() is None


def test_deleting_a_custody_receipt_does_not_reopen_sealed_authority(
    tmp_path: Path,
) -> None:
    root = tmp_path / "deleted-seal"
    store = ConceptricStore(root)
    store.append(_wake())
    store.seal_custody(store_role="test-fixture")
    store.custody_receipt_path.unlink()

    with pytest.raises(StoreError, match="custody receipt is missing"):
        ConceptricStore(root)


def test_expected_role_refuses_a_whole_store_cross_role_transplant(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blueprint"
    blueprint = ConceptricStore(
        source, expected_store_role="blueprint-generation"
    )
    blueprint.append(_wake())
    blueprint.seal_custody(store_role="blueprint-generation")

    transplanted = tmp_path / "runtime"
    shutil.copytree(source, transplanted)

    with pytest.raises(StoreError, match="caller's authority anchor"):
        ConceptricStore(
            transplanted, expected_store_role="live-runtime-fabric"
        )
    with pytest.raises(StoreError, match="caller's authority anchor"):
        ConceptricStore(
            transplanted,
            read_only=True,
            expected_store_role="live-runtime-fabric",
        )


def test_later_unanchored_caller_cannot_relabel_an_anchored_store(
    tmp_path: Path,
) -> None:
    root = tmp_path / "anchored-runtime"
    anchored = ConceptricStore(
        root, expected_store_role="live-runtime-fabric"
    )
    anchored.append(_wake())

    with pytest.raises(StoreError, match="relabel an anchored store"):
        ConceptricStore(root).seal_custody(store_role="blueprint-generation")


def test_expected_role_open_does_not_rewrite_an_already_sealed_identity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "older-sealed-runtime"
    original = ConceptricStore(root)
    original.append(_wake())
    original.seal_custody(store_role="live-runtime-fabric")
    receipt_before = original.custody_receipt_path.read_bytes()

    reopened = ConceptricStore(
        root, expected_store_role="live-runtime-fabric"
    )

    assert reopened.custody_receipt_path.read_bytes() == receipt_before
    with sqlite3.connect(reopened.path) as connection:
        assert connection.execute(
            "SELECT value FROM meta WHERE key = 'store_role_anchor_json'"
        ).fetchone() is None


def test_custody_seal_and_verifier_refuse_orphans_wal_and_receipt_drift(
    tmp_path: Path,
) -> None:
    orphaned = ConceptricStore(tmp_path / "orphaned")
    orphaned.append(_wake())
    orphaned.hive.put(b"unmarked")
    with pytest.raises(StoreError, match="outside the causal ledger mark set"):
        orphaned.seal_custody(store_role="test-fixture")

    root = tmp_path / "wal"
    store = ConceptricStore(root)
    store.append(_wake())
    store.seal_custody(store_role="test-fixture")
    store.append(_sew())
    assert store._wal_path().stat().st_size > 0
    with pytest.raises(StoreError, match="uncheckpointed WAL"):
        ConceptricStore(root, read_only=True).verify_custody()

    store.seal_custody(store_role="test-fixture")
    raw = json.loads(store.custody_receipt_path.read_text(encoding="utf-8"))
    raw["event_count"] = 0
    store.custody_receipt_path.write_text(canonical_json(raw) + "\n", encoding="utf-8")
    with pytest.raises(StoreError, match="custody receipt disagrees"):
        ConceptricStore(root, read_only=True).verify_custody()


def test_custody_verifier_reads_the_claims_vocabulary(tmp_path: Path) -> None:
    root = tmp_path / "claims"
    store = ConceptricStore(root)
    store.append(_wake())
    store.seal_custody(store_role="test-fixture")
    raw = json.loads(store.custody_receipt_path.read_text(encoding="utf-8"))
    raw["claims"]["zero_orphans"] = False
    store.custody_receipt_path.write_text(canonical_json(raw) + "\n", encoding="utf-8")

    with pytest.raises(StoreError, match="custody receipt disagrees"):
        ConceptricStore(root, read_only=True).verify_custody()


@pytest.mark.parametrize("relabelled_face", ["receipt", "ledger"])
def test_custody_verifier_refuses_production_role_relabelling(
    tmp_path: Path, relabelled_face: str
) -> None:
    root = tmp_path / relabelled_face
    store = ConceptricStore(root)
    store.append(_wake())
    store.seal_custody(store_role="test-fixture")
    production_identity = {
        "schema_version": "atlas.store-identity/1",
        "role": "production-blueprint",
        "database_ref": "conceptric.sqlite3",
    }
    if relabelled_face == "receipt":
        raw = json.loads(store.custody_receipt_path.read_text(encoding="utf-8"))
        raw["store_identity"] = production_identity
        store.custody_receipt_path.write_text(canonical_json(raw) + "\n", encoding="utf-8")
    else:
        with sqlite3.connect(store.path) as connection:
            connection.execute(
                "UPDATE meta SET value = ? WHERE key = 'store_identity_json'",
                (canonical_json(production_identity),),
            )
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    with pytest.raises(StoreError, match="concrete non-production store role"):
        ConceptricStore(root, read_only=True).verify_custody()


def test_genesis_refuses_missing_ledger_beside_receipts_or_hive_bytes(tmp_path: Path) -> None:
    for marker in ("migration", "seal", "legacy", "hive"):
        root = tmp_path / marker
        root.mkdir()
        if marker == "migration":
            (root / "hive-migration-receipt.json").write_text("{}\n", encoding="utf-8")
        elif marker == "seal":
            (root / "hive-custody-receipt.json").write_text("{}\n", encoding="utf-8")
        elif marker == "legacy":
            (root / "events.legacy-imported.jsonl").write_text("{}\n", encoding="utf-8")
        else:
            chunk = root / DEFAULT_EVENT_HIVE_REF / "aa" / ("a" * 64 + ".zlib")
            chunk.parent.mkdir(parents=True)
            chunk.write_bytes(b"custody survived")
        with pytest.raises(StoreError, match="genesis refused"):
            ConceptricStore(root)
        assert not (root / "conceptric.sqlite3").exists()


@pytest.mark.parametrize("sibling", ["RECEIPT.json", "blobs/body", "conceptric.sqlite3-wal"])
def test_genesis_refuses_missing_ledger_beside_any_persistent_sibling(
    tmp_path: Path, sibling: str
) -> None:
    root = tmp_path / sibling.replace("/", "-")
    path = root / sibling
    path.parent.mkdir(parents=True)
    path.write_bytes(b"surviving authority evidence")

    with pytest.raises(StoreError, match="genesis refused"):
        ConceptricStore(root)

    assert not (root / "conceptric.sqlite3").exists()


@pytest.mark.parametrize("ledger_shape", ["zero", "tableless", "truncated", "lfs-pointer"])
def test_genesis_refuses_unusable_existing_ledger_beside_custody(
    tmp_path: Path, ledger_shape: str
) -> None:
    root = tmp_path / ledger_shape
    root.mkdir()
    ledger = root / "conceptric.sqlite3"
    if ledger_shape == "zero":
        ledger.touch()
    elif ledger_shape == "tableless":
        with sqlite3.connect(ledger) as connection:
            connection.execute("PRAGMA application_id = 1096041805")
    elif ledger_shape == "truncated":
        ledger.write_bytes(b"SQLite format 3\0" + (b"torn" * 13))
    else:
        ledger.write_text(
            "version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{'a' * 64}\nsize 24576\n",
            encoding="ascii",
        )
    before = ledger.read_bytes()
    (root / "hive-custody-receipt.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(StoreError, match="genesis refused"):
        ConceptricStore(root)

    assert ledger.read_bytes() == before


@pytest.mark.parametrize("replacement_kind", ["own-genesis", "foreign-ledger"])
def test_genesis_refuses_valid_schema_ledger_not_bound_to_custody_evidence(
    tmp_path: Path, replacement_kind: str
) -> None:
    root = tmp_path / "sealed-authority"
    authority = ConceptricStore(root)
    authority.append_many((_wake(), _sew()))
    authority.seal_custody(store_role="test-fixture")

    replacement_root = tmp_path / replacement_kind
    replacement = ConceptricStore(replacement_root)
    if replacement_kind == "foreign-ledger":
        replacement.append_many((_foreign_wake(), _sew()))
        replacement.seal_custody(store_role="test-fixture")
    else:
        with sqlite3.connect(replacement.path) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    shutil.copy2(replacement.path, authority.path)
    poisoned = authority.path.read_bytes()

    with pytest.raises(StoreError, match="genesis refused") as exc:
        ConceptricStore(root)

    assert "custody evidence" in str(exc.value)
    assert authority.path.read_bytes() == poisoned


def test_custody_admission_accepts_an_exact_sealed_prefix_with_later_appends(
    tmp_path: Path,
) -> None:
    root = tmp_path / "continued-authority"
    store = ConceptricStore(root)
    first = store.append(_wake())
    store.seal_custody(store_role="test-fixture")
    second = store.append(_sew())

    cold = ConceptricStore(root)

    assert [event.event_id for event in cold.events()] == [
        first.event.event_id,
        second.event.event_id,
    ]


def test_travelling_snapshot_receipt_requires_explicit_restore_before_writable_open(
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime-snapshot"
    store = ConceptricStore(root)
    stored = store.append(_wake())
    (root / "RECEIPT.json").write_text("{}\n", encoding="utf-8")

    assert ConceptricStore(root, read_only=True).events()[0].event_id == stored.event.event_id
    with pytest.raises(StoreError, match="explicit restore act"):
        ConceptricStore(root)


def test_explicit_v1_migration_preserves_replay_and_append_door(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    store = _legacy_v1_store(root)
    stale_writer = ConceptricStore(root)
    before = store.replay()
    assert store.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA
    assert stale_writer.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA
    token_before = ConceptricStore.read_drift_token(root)

    receipt = store.migrate_hived(store_role="test-fixture")

    assert receipt["status"] == "migrated"
    assert receipt["store_identity"] == {
        "schema_version": "atlas.store-identity/1",
        "role": "test-fixture",
        "database_ref": "conceptric.sqlite3",
    }
    assert receipt["authorization_scope"]["storage_and_wall_clock_measurements"] == (
        "absent-non-authorizing"
    )
    assert receipt["source_event_chain_root"].startswith("sha256:")
    assert receipt["source_meta_root"].startswith("sha256:")
    assert receipt["event_count"] == 1
    assert receipt["reachability"]["status"] == "exact"
    assert receipt["reachability"]["orphan_handles"] == ()
    assert store.custody_receipt_path.is_file()
    assert store.verify_custody()["migration"]["event_count"] == 1
    assert store.schema_version == CONCEPTRIC_DB_SCHEMA
    assert store.replay() == before
    assert ConceptricStore.read_drift_token(root) == token_before
    assert not (root / "conceptric.v1.sqlite3").exists()
    with sqlite3.connect(store.path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(events)")}
        assert "event_handle" in columns and "event_json" not in columns
        assert connection.execute(
            "SELECT value FROM meta WHERE key = 'legacy_jsonl_sha256'"
        ).fetchone()[0] == "sha256:" + ("b" * 64)
        assert connection.execute(
            "SELECT value FROM meta WHERE key = 'migration_source_meta_root'"
        ).fetchone()[0].startswith("sha256:")

    stale_writer.append(_sew())
    assert stale_writer.schema_version == CONCEPTRIC_DB_SCHEMA
    refreshed = stale_writer.seal_custody(store_role="test-fixture")
    assert refreshed["event_count"] == 2
    assert refreshed["migration"]["event_count"] == 1
    cold = ConceptricStore(root)
    assert len(cold.events()) == 2
    assert cold.replay().head_event_id == cold.events()[-1].event_id


def test_v1_migration_quarantines_old_sqlite_sidecars_before_candidate_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "legacy-sidecars"
    store = _legacy_v1_store(root)
    attempted: list[str] = []
    retire = store._retire_disposable_obstruction

    def observed(path: Path):
        attempted.append(path.name)
        return retire(path)

    monkeypatch.setattr(store, "_retire_disposable_obstruction", observed)
    store.migrate_hived(store_role="test-fixture", retain_v1_receipt=True)

    assert "conceptric.sqlite3-wal" in attempted
    assert "conceptric.sqlite3-shm" in attempted
    assert store.verify_custody()["event_count"] == 1


def test_explicit_recovery_seals_only_an_exact_incomplete_hived_migration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "incomplete-migration"
    store = _legacy_v1_store(root)
    migrated = store.migrate_hived(
        store_role="test-fixture", retain_v1_receipt=True
    )
    store.custody_receipt_path.unlink()

    with pytest.raises(StoreError, match="custody receipt is missing"):
        ConceptricStore(root, expected_store_role="test-fixture")

    recovered = ConceptricStore.recover_incomplete_hived_migration(
        root, store_role="test-fixture"
    )

    assert recovered["event_count"] == migrated["event_count"]
    assert recovered["head_digest"] == migrated["head_digest"]
    assert recovered["migration"]["event_count"] == migrated["event_count"]
    assert ConceptricStore(
        root, read_only=True, expected_store_role="test-fixture"
    ).verify_custody() == recovered
    reopened = ConceptricStore(root, expected_store_role="test-fixture")
    assert reopened.current_state().event_count == migrated["event_count"]


@pytest.mark.parametrize(
    ("field", "mutated"),
    [
        ("status", "prepared"),
        ("source_schema", CONCEPTRIC_DB_SCHEMA),
        ("source_event_chain_root", "sha256:" + ("0" * 64)),
        ("source_meta_root", "sha256:" + ("0" * 64)),
    ],
)
def test_migration_receipt_is_bound_to_the_surviving_causal_prefix(
    tmp_path: Path, field: str, mutated: str
) -> None:
    root = tmp_path / field
    store = _legacy_v1_store(root)
    store.migrate_hived(store_role="test-fixture")
    raw = json.loads(store.migration_receipt_path.read_text(encoding="utf-8"))
    raw[field] = mutated
    store.migration_receipt_path.write_text(canonical_json(raw) + "\n", encoding="utf-8")

    with pytest.raises(StoreError, match="causal ledger prefix"):
        ConceptricStore(root, read_only=True).verify_custody()


def test_migration_refuses_ambiguous_production_role_without_mutation(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    store = _legacy_v1_store(root)
    before = store.path.read_bytes()

    with pytest.raises(StoreError, match="concrete non-production store role"):
        store.migrate_hived(store_role="production-blueprint")

    assert store.path.read_bytes() == before
    assert store.schema_version == LEGACY_CONCEPTRIC_DB_SCHEMA
    assert not store.migration_receipt_path.exists()


def test_authority_checkpoint_fast_deep_roots_are_exact(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path)
    store.append(_wake())

    fast = ConceptricStore.read_authority_checkpoint(tmp_path)
    cached = ConceptricStore.read_authority_checkpoint(tmp_path)
    parity = ConceptricStore.verify_authority_checkpoint_deep(tmp_path)

    assert fast["status"] == "CURRENT"
    assert fast["anchor_checkpoint"] == fast["effective_checkpoint"]
    assert fast["anchor_checkpoint_digest"] == fast["effective_checkpoint_digest"]
    assert fast["checkpoint_digest"] == chash(fast["checkpoint"])
    assert fast["read_metrics"]["ledger_rows_loaded"] == 1
    assert cached["read_metrics"]["tip_cache_hit"] is True
    assert fast["read_metrics"]["global_history_replayed"] is False
    authority = fast["checkpoint"]["authority"]
    assert authority["seat_occupancy_root"] == chash(
        {
            "schema_version": "atlas.seat-occupancy-accumulator/1",
            "occupancy": authority["seat_occupancy"],
        }
    )
    assert authority["region_lease_root"] == chash(
        {
            "schema_version": "atlas.region-lease-accumulator/1",
            "leases": authority["region_leases"],
        }
    )
    assert parity["status"] == "EXACT"
    assert parity["fast_deep_equal"] is True


def test_default_authority_context_infers_the_anchored_store_role(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path, expected_store_role="blueprint-fixture")
    store.append(_wake())

    verified = ConceptricStore.read_authority_checkpoint(tmp_path)

    assert verified["status"] == "CURRENT"


@pytest.mark.parametrize("suffix_count", [0, 1, 64])
def test_read_atlas_object_does_not_use_writer_checkpoint_suffix(
    tmp_path: Path, suffix_count: int
) -> None:
    store = ConceptricStore(tmp_path)
    declared = store.append(_wake())
    object_id = f"event:{declared.event.event_id}"
    if suffix_count:
        with store._connect() as ledger:
            anchor = ledger.execute(
                "SELECT checkpoint_json, checkpoint_digest FROM authority_checkpoint"
            ).fetchone()
            anchor_pair = (anchor["checkpoint_json"], anchor["checkpoint_digest"])
        store.append_many(_unrelated(index) for index in range(suffix_count))
        with store._connect() as ledger:
            ledger.execute(
                "UPDATE authority_checkpoint SET checkpoint_json = ?, checkpoint_digest = ?",
                anchor_pair,
            )
            ledger.commit()

    result = ConceptricStore.read_atlas_object(tmp_path, reference=object_id)
    verified = ConceptricStore.verify_atlas_object_current_root(
        tmp_path,
        reference=object_id,
        expected_current_root=result["current_root"],
    )

    assert result["status"] == "CURRENT"
    assert result["integrity_boundary"] == "CHECKSUMMED-CRUTCH"
    assert result["authenticated"] is False
    assert result["current"] is True
    assert result["clean"] is True
    assert result["authority_suffix_count"] == 0
    assert result["authority_suffix_limit"] == 64
    assert result["reference_kind"] == "graph-object"
    assert result["value"]["object_id"] == object_id
    assert result["content_handle"] == chash(result["value"])
    assert result["read_metrics"]["suffix_rows_loaded"] == 0
    assert result["read_metrics"]["checkpoint_rows_loaded"] == 0
    assert result["provenance"]["writer_authority_checkpoint_used"] is False
    assert result["read_metrics"]["projection_rows_loaded"] == 1
    assert result["read_metrics"]["declaration_event_rows_loaded"] == 1
    assert result["read_metrics"]["global_history_replayed"] is False
    assert result["fidelity_boundary"]["sidecar_residual"] == (
        "sidecar-duplicate-nonleaf"
    )
    assert verified["status"] == "CURRENT"
    assert verified["integrity_boundary"] == "CHECKSUMMED-CRUTCH"
    assert verified["authenticated"] is False
    assert verified["authority_suffix_count"] == 0
    assert verified["authority_suffix_limit"] == 64
    assert verified["read_only"] is True
    assert verified["authority_write"] == "none"


def test_keyed_atlas_object_ignores_writer_checkpoint_beyond_64_row_suffix(
    tmp_path: Path,
) -> None:
    store = ConceptricStore(tmp_path)
    declared = store.append(_wake())
    with store._connect() as ledger:
        anchor = ledger.execute(
            "SELECT checkpoint_json, checkpoint_digest FROM authority_checkpoint"
        ).fetchone()
        anchor_pair = (anchor["checkpoint_json"], anchor["checkpoint_digest"])
    store.append_many(_unrelated(index) for index in range(65))
    with store._connect() as ledger:
        ledger.execute(
            "UPDATE authority_checkpoint SET checkpoint_json = ?, checkpoint_digest = ?",
            anchor_pair,
        )
        ledger.commit()

    result = ConceptricStore.read_atlas_object(
        tmp_path,
        reference=f"event:{declared.event.event_id}",
    )
    assert result["status"] == "CURRENT"
    assert result["read_metrics"]["checkpoint_rows_loaded"] == 0
    with pytest.raises(HistoryChainMismatch, match="exceeds the bounded"):
        ConceptricStore.read_authority_checkpoint(tmp_path)


def test_read_only_open_and_keyed_read_do_not_require_writer_checkpoint(
    tmp_path: Path,
) -> None:
    store = ConceptricStore(tmp_path)
    declared = store.append(_wake())
    with store._connect() as ledger:
        ledger.execute("DROP TABLE authority_checkpoint")
        ledger.commit()

    opened = ConceptricStore(tmp_path, read_only=True)
    result = opened.read_atlas_object(
        tmp_path,
        reference=f"event:{declared.event.event_id}",
    )
    assert result["status"] == "CURRENT"
    assert result["provenance"]["writer_authority_checkpoint_used"] is False
    assert result["read_metrics"]["checkpoint_rows_loaded"] == 0


def test_keyed_atlas_object_refuses_missing_dirty_and_moved_projection(
    tmp_path: Path,
) -> None:
    store = ConceptricStore(tmp_path)
    declared = store.append(_wake())
    object_id = f"event:{declared.event.event_id}"

    with pytest.raises(StoreError) as missing:
        ConceptricStore.read_atlas_object(tmp_path, reference="seat:missing")
    assert missing.value.detail["code"] == "NOT_FOUND"

    with sqlite3.connect(store.projection_path) as projection:
        projection.execute(
            "UPDATE objects SET object_json = ? WHERE object_id = ?",
            ('{"tampered":true}', object_id),
        )
    with pytest.raises(HistoryChainMismatch) as dirty:
        ConceptricStore.read_atlas_object(tmp_path, reference=object_id)
    assert dirty.value.detail["code"] == "DIRTY"

    ConceptricStore(tmp_path)
    current = ConceptricStore.read_atlas_object(tmp_path, reference=object_id)
    with sqlite3.connect(store.projection_path) as projection:
        projection.execute(
            "UPDATE meta SET value = ? WHERE key = 'authoritative_head_digest'",
            (GENESIS_DIGEST,),
        )
    with pytest.raises(HistoryChainMismatch) as moved:
        ConceptricStore.read_atlas_object(tmp_path, reference=object_id)
    assert moved.value.detail["code"] == "MOVED"

    ConceptricStore(tmp_path)
    store.append(_unrelated(999))
    with pytest.raises(HistoryChainMismatch) as stale_root:
        ConceptricStore.verify_atlas_object_current_root(
            tmp_path,
            reference=object_id,
            expected_current_root=current["current_root"],
        )
    assert stale_root.value.detail["code"] == "MOVED"


def test_keyed_graph_lookup_ignores_100k_unrelated_rows_and_uses_primary_key_10k_times(
    tmp_path: Path,
) -> None:
    store = ConceptricStore(tmp_path)
    declared = store.append(_wake())
    object_id = f"event:{declared.event.event_id}"
    with sqlite3.connect(store.projection_path) as projection:
        target = projection.execute(
            "SELECT kind, content_handle, assumption, fibre, grade_contract_id, "
            "grade_coordinate_json, declared_event_id, object_json "
            "FROM objects WHERE object_id = ?",
            (object_id,),
        ).fetchone()
        assert target is not None
        for start in range(0, 100_000, 1_000):
            rows = []
            for index in range(start, start + 1_000):
                unrelated_id = f"unrelated:{index:06d}"
                unrelated = json.loads(target[7])
                unrelated["object_id"] = unrelated_id
                rows.append(
                    (
                        unrelated_id,
                        *target[:7],
                        canonical_json(unrelated),
                    )
                )
            projection.executemany(
                "INSERT INTO objects(object_id, kind, content_handle, assumption, fibre, "
                "grade_contract_id, grade_coordinate_json, declared_event_id, object_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        plan = " ".join(
            str(field)
            for field in projection.execute(
                "EXPLAIN QUERY PLAN SELECT object_json FROM objects WHERE object_id = ?",
                (object_id,),
            ).fetchone()
        )
        for _ in range(10_000):
            row = projection.execute(
                "SELECT object_json FROM objects WHERE object_id = ?",
                (object_id,),
            ).fetchone()
            assert row is not None

    result = ConceptricStore.read_atlas_object(tmp_path, reference=object_id)
    assert "PRIMARY KEY" in plan or "objects" in plan
    assert result["value"]["object_id"] == object_id
    assert result["read_metrics"]["projection_rows_loaded"] == 1
    assert result["read_metrics"]["global_history_replayed"] is False


def test_missing_checkpoint_stays_readable_and_is_refreshed_by_ordinary_append(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path)
    store.append(_wake())
    with store._connect() as ledger:
        ledger.execute("DROP TABLE authority_checkpoint")
        ledger.commit()

    absent = ConceptricStore.read_authority_checkpoint(tmp_path)
    legacy = ConceptricStore.read_provider_seat_binding(
        tmp_path, provider_session_ref="codex:legacy"
    )
    assert absent["status"] == "NO-CHECKPOINT"
    assert absent["mode"] == "legacy-deep"
    assert legacy["fidelity_boundary"]["status"] == "LEGACY-DEEP"
    assert legacy["read_metrics"]["history_replayed"] is True

    writer = ConceptricStore(tmp_path)
    with writer._connect() as ledger:
        table = ledger.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'authority_checkpoint'"
        ).fetchone()
    assert table is None

    before = ConceptricStore.read_drift_token(tmp_path)
    writer.append(_sew())
    adopted = ConceptricStore.read_authority_checkpoint(tmp_path)
    assert adopted["status"] == "CURRENT"
    assert adopted["checkpoint"]["cursor"] == 2
    assert ConceptricStore.read_drift_token(tmp_path)["head_record_digest"] != before["head_record_digest"]


@pytest.mark.parametrize(
    "kind",
    [
        EventKind.LIFECYCLE,
        EventKind.SEAT,
        EventKind.SEAT_JOIN,
        EventKind.SEAT_OCCUPANCY_BINDING,
        EventKind.REGION_CHECKOUT,
        EventKind.REGION_CHECKIN,
        EventKind.REGION_PUBLICATION_PREPARED,
        EventKind.REGION_PUBLICATION_SIGNED,
        EventKind.REGION_PUBLICATION_AUTHORIZED,
        EventKind.REGION_PUBLICATION_FINALIZED,
        EventKind.ASSUMPTION,
        EventKind.TRANSPORT,
        EventKind.CORPUS_ACT,
        EventKind.REPL,
        EventKind.MESSAGE,
        EventKind.MESSAGE_PULL,
        EventKind.MESSAGE_ACK,
        EventKind.MESSAGE_PRESERVE_FORK,
        EventKind.MESSAGE_SUPERSESSION,
        EventKind.MESSAGE_MIGRATION_SUPERSESSION,
        EventKind.MESSAGE_EXPIRY,
    ],
)
def test_authority_checkpoint_refuses_each_accumulator_changing_suffix_kind(
    tmp_path: Path, kind: EventKind
) -> None:
    store = ConceptricStore(tmp_path)
    stored_wake = store.append(_wake())
    event = AtlasEvent.create(
        occurred_at="2026-08-24T12:02:00Z",
        kind=kind,
        producer=SeatRole.SYSTEM,
        actor=SeatRole.SYSTEM,
        subject=f"authority-suffix:{kind.value}",
        assumption=None,
        fibre=None,
        correlation_id="authority-affecting-suffix",
        causation_ids=(),
        provenance=(SOURCE,),
        residual=RESIDUAL,
        runtime=RUNTIME,
        producer_ref=ProducerRef("pytest", "system", "test"),
        validity=Validity.REFUSED,
        payload={
            "schema_version": "test.authority-affecting-suffix/1",
            "suffix_fixture": kind.value,
        },
    )
    stored = StoredEvent.create(2, stored_wake.record_digest, event)
    handle = store.hive.put(canonical_json(event.to_dict()).encode())
    with store._connect() as ledger:
        store._insert_event_v2(ledger, stored, handle)
        ledger.execute(
            "UPDATE meta SET value = ? WHERE key = 'authoritative_head_digest'",
            (stored.record_digest,),
        )
        ledger.commit()

    assert kind.value in AUTHORITY_AFFECTING_EVENT_KINDS
    with pytest.raises(HistoryChainMismatch, match="uncheckpointed authority transition"):
        ConceptricStore.read_authority_checkpoint(tmp_path)


@pytest.mark.parametrize(
    "field",
    ["implementation_digest", "environment_root", "dirty_paths_root"],
)
def test_authority_checkpoint_context_mismatch_refuses(tmp_path: Path, field: str) -> None:
    store = ConceptricStore(tmp_path)
    store.append(_wake())
    changed = dict(store._authority_context)
    changed[field] = "sha256:" + ("f" * 64)

    with pytest.raises(HistoryChainMismatch, match="context is UNKNOWN"):
        ConceptricStore.read_authority_checkpoint(tmp_path, expected_context=changed)


def test_authority_checkpoint_moved_store_refuses(tmp_path: Path) -> None:
    source = tmp_path / "source"
    moved = tmp_path / "moved"
    store = ConceptricStore(source)
    store.append(_wake())
    shutil.copytree(source, moved)

    with pytest.raises(HistoryChainMismatch, match="context is UNKNOWN"):
        ConceptricStore.read_authority_checkpoint(moved)


def test_authority_checkpoint_digest_and_head_hive_corruption_refuse(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path)
    stored = store.append(_wake())
    with store._connect() as ledger:
        ledger.execute(
            "UPDATE authority_checkpoint SET checkpoint_digest = ? WHERE singleton = 1",
            ("sha256:" + ("0" * 64),),
        )
        ledger.commit()
    with pytest.raises(HistoryChainMismatch, match="digest does not verify"):
        ConceptricStore.read_authority_checkpoint(tmp_path)

    with store._connect() as ledger:
        checkpoint = store._checkpoint_for_state(
            store._verified_state, head_record_digest=stored.record_digest
        )
        store._write_checkpoint(ledger, checkpoint)
        handle = ledger.execute(
            "SELECT event_handle FROM events WHERE sequence = 1"
        ).fetchone()["event_handle"]
        ledger.commit()
    store.hive.key_path(handle).write_bytes(b"corrupt")
    with pytest.raises((HistoryChainMismatch, BlobHashMismatch)):
        ConceptricStore.read_authority_checkpoint(tmp_path)


def test_authority_checkpoint_verifies_64_row_non_authority_suffix_and_refuses_65(
    tmp_path: Path,
) -> None:
    for suffix_count in (1, 64):
        bounded = tmp_path / f"bounded-{suffix_count}"
        store = ConceptricStore(bounded)
        store.append(_wake())
        with store._connect() as ledger:
            anchor = ledger.execute(
                "SELECT checkpoint_json, checkpoint_digest FROM authority_checkpoint"
            ).fetchone()
            anchor_pair = (anchor["checkpoint_json"], anchor["checkpoint_digest"])
        store.append_many(_unrelated(index) for index in range(suffix_count))
        with store._connect() as ledger:
            ledger.execute(
                "UPDATE authority_checkpoint SET checkpoint_json = ?, checkpoint_digest = ?",
                anchor_pair,
            )
            ledger.commit()
        verified = ConceptricStore.read_authority_checkpoint(bounded)
        assert verified["status"] == "CURRENT"
        assert verified["read_metrics"]["suffix_rows_loaded"] == suffix_count
        assert verified["read_metrics"]["authority_tail_events"] == 0
        assert verified["anchor_checkpoint_digest"] == anchor_pair[1]
        assert verified["anchor_checkpoint_digest"] == chash(
            verified["anchor_checkpoint"]
        )
        assert verified["effective_checkpoint_digest"] == chash(
            verified["effective_checkpoint"]
        )
        assert verified["checkpoint"] == verified["effective_checkpoint"]
        assert verified["checkpoint_digest"] == verified["effective_checkpoint_digest"]
        assert verified["anchor_checkpoint_digest"] != verified["effective_checkpoint_digest"]

    over = tmp_path / "over"
    store = ConceptricStore(over)
    store.append(_wake())
    with store._connect() as ledger:
        anchor = ledger.execute(
            "SELECT checkpoint_json, checkpoint_digest FROM authority_checkpoint"
        ).fetchone()
        anchor_pair = (anchor["checkpoint_json"], anchor["checkpoint_digest"])
    store.append_many(_unrelated(index) for index in range(65))
    with store._connect() as ledger:
        ledger.execute(
            "UPDATE authority_checkpoint SET checkpoint_json = ?, checkpoint_digest = ?",
            anchor_pair,
        )
        ledger.commit()
    with pytest.raises(HistoryChainMismatch, match="exceeds the bounded"):
        ConceptricStore.read_authority_checkpoint(over)
    parity = ConceptricStore.verify_authority_checkpoint_deep(over)
    assert parity["status"] == "CONTEST"
    assert parity["verified_predecessor"] == anchor_pair[1]
    assert parity["candidate_checkpoint"]["cursor"] == 66
    assert parity["fast_deep_equal"] is False


def test_deep_checkpoint_verifier_reports_corrupt_forged_and_context_moved_cache(
    tmp_path: Path,
) -> None:
    store = ConceptricStore(tmp_path)
    store.append(_wake())
    with store._connect() as ledger:
        original = ledger.execute(
            "SELECT checkpoint_json, checkpoint_digest FROM authority_checkpoint"
        ).fetchone()
        original_pair = (str(original["checkpoint_json"]), str(original["checkpoint_digest"]))
        ledger.execute(
            "UPDATE authority_checkpoint SET checkpoint_json = ? WHERE singleton = 1",
            ("{",),
        )
        ledger.commit()
    malformed = ConceptricStore.verify_authority_checkpoint_deep(tmp_path)
    assert malformed["status"] == "REFUSED"
    assert malformed["verified_predecessor"] is None
    assert malformed["candidate_checkpoint"]["cursor"] == 1

    body = json.loads(original_pair[0])
    body["authority"]["seat_occupancy_root"] = "sha256:" + ("f" * 64)
    with store._connect() as ledger:
        ledger.execute(
            "UPDATE authority_checkpoint SET checkpoint_json = ?, checkpoint_digest = ?",
            (canonical_json(body), chash(body)),
        )
        ledger.commit()
    forged = ConceptricStore.verify_authority_checkpoint_deep(tmp_path)
    assert forged["status"] == "REFUSED"
    assert forged["verified_predecessor"] is None

    with store._connect() as ledger:
        ledger.execute(
            "UPDATE authority_checkpoint SET checkpoint_json = ?, checkpoint_digest = ?",
            original_pair,
        )
        ledger.commit()
    moved = dict(store._authority_context)
    moved["implementation_digest"] = "sha256:" + ("e" * 64)
    context = ConceptricStore.verify_authority_checkpoint_deep(
        tmp_path, expected_context=moved
    )
    assert context["status"] == "CONTEST"
    assert set(context["context_disagreements"]) == {"implementation_digest"}
    assert context["verified_predecessor"] == original_pair[1]


def test_checkpoint_adoption_cas_rebinds_only_verified_predecessor(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path)
    store.append(_wake())
    before = ConceptricStore.read_drift_token(tmp_path)
    with store._connect() as ledger:
        row = ledger.execute(
            "SELECT checkpoint_json FROM authority_checkpoint WHERE singleton = 1"
        ).fetchone()
        body = json.loads(str(row["checkpoint_json"]))
        body["implementation_digest"] = "sha256:" + ("d" * 64)
        predecessor = chash(body)
        ledger.execute(
            "UPDATE authority_checkpoint SET checkpoint_json = ?, checkpoint_digest = ?",
            (canonical_json(body), predecessor),
        )
        ledger.commit()

    with pytest.raises(HistoryChainMismatch, match="predecessor moved"):
        ConceptricStore.prepare_authority_checkpoint(
            tmp_path,
            expected_predecessor="sha256:" + ("0" * 64),
            authority_context=store._authority_context,
        )
    with store._connect() as ledger:
        still = ledger.execute(
            "SELECT checkpoint_digest FROM authority_checkpoint WHERE singleton = 1"
        ).fetchone()
    assert str(still["checkpoint_digest"]) == predecessor
    assert ConceptricStore.read_drift_token(tmp_path) == before

    adopted = ConceptricStore.prepare_authority_checkpoint(
        tmp_path,
        expected_predecessor=predecessor,
        authority_context=store._authority_context,
    )
    assert adopted["predecessor"] == predecessor
    assert adopted["event_append"] is False
    assert ConceptricStore.read_drift_token(tmp_path) == before
    assert ConceptricStore.verify_authority_checkpoint_deep(tmp_path)["status"] == "EXACT"


def test_portable_checkpoint_adoption_is_atomic_resumable_and_writable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source-filesystem" / "runtime"
    original = ConceptricStore(
        source, expected_store_role="live-runtime-fabric"
    )
    stored = original.append(_wake())
    original.seal_custody(store_role="live-runtime-fabric")
    source_fast = ConceptricStore.read_authority_checkpoint(
        source, expected_context=original._authority_context
    )

    recovered = tmp_path / "blank-machine" / "runtime"
    shutil.copytree(source, recovered)
    target_context = ConceptricStore.authority_context_manifest(
        recovered, store_role="live-runtime-fabric"
    )
    target_context_evidence = ConceptricStore.authority_context_evidence(
        recovered, store_role="live-runtime-fabric"
    )
    source_context_evidence = ConceptricStore.authority_context_evidence(
        source, store_role="live-runtime-fabric"
    )
    deep = ConceptricStore.verify_authority_checkpoint_deep(
        recovered,
        expected_context=target_context,
        expected_store_role="live-runtime-fabric",
    )
    assert deep["status"] == "CONTEST"
    assert set(deep["disagreements"]) <= {
        "implementation_digest",
        "environment_root",
        "dirty_paths_root",
    }
    assert deep["verified_predecessor"] == source_fast["checkpoint_digest"]
    before = ConceptricStore.read_drift_token(recovered, immutable=True)
    source_ledger_sha256 = sha256_file(recovered / "conceptric.sqlite3")

    def portable_fields(predecessor: str) -> dict:
        grant_identity = {
            "schema_version": "laplace.portable-runtime-adoption-grant/1",
            "source_snapshot_id": "sha256:" + ("1" * 64),
            "source_receipt_sha256": "sha256:" + ("2" * 64),
            "source_checkpoint_digest": predecessor,
            "recovery_coordinate_payload_digest": "sha256:" + ("6" * 64),
            "recovery_grant_anchor_root": "sha256:" + ("7" * 64),
            "destination_root": str(recovered.resolve()),
            "destination_context_evidence_root": target_context_evidence[
                "evidence_root"
            ],
            "target_store_role": "live-runtime-fabric",
            "target_store_schema": CONCEPTRIC_DB_SCHEMA,
            "predecessor_adoption_root": "sha256:" + ("8" * 64),
        }
        return {
            "source_blob_manifest_root": "sha256:" + ("3" * 64),
            "source_event_hive_manifest_root": "sha256:" + ("4" * 64),
            "source_evidence_manifest_root": "sha256:" + ("5" * 64),
            "source_authority_context_evidence": source_context_evidence,
            "source_git_commit": "a" * 40,
            "source_git_tree": "b" * 40,
            "recovery_coordinate_payload_digest": "sha256:" + ("6" * 64),
            "predecessor_adoption_root": "sha256:" + ("8" * 64),
            "grant_root": chash(grant_identity),
            "grant_identity": grant_identity,
            "target_context_evidence": target_context_evidence,
            "target_canonical_root": recovered,
        }

    ledger_before_refusal = (recovered / "conceptric.sqlite3").read_bytes()
    with pytest.raises(HistoryChainMismatch, match="predecessor moved"):
        ConceptricStore.prepare_portable_authority_checkpoint(
            recovered,
            expected_predecessor="sha256:" + ("0" * 64),
            authority_context=target_context,
            expected_store_role="live-runtime-fabric",
            source_snapshot_id="sha256:" + ("1" * 64),
            source_receipt_sha256="sha256:" + ("2" * 64),
            source_ledger_sha256=source_ledger_sha256,
            source_cursor=1,
            source_head_event_id=stored.event.event_id,
            source_head_record_digest=stored.record_digest,
            **portable_fields("sha256:" + ("0" * 64)),
        )
    assert (recovered / "conceptric.sqlite3").read_bytes() == ledger_before_refusal
    assert ConceptricStore.read_portable_authority_adoption(
        recovered, expected_store_role="live-runtime-fabric"
    ) is None

    forged_source = json.loads(json.dumps(source_context_evidence))
    forged_source["manifest"]["runtime"]["platform"] = "foreign-platform"
    forged_source["roots"]["environment_root"] = chash(
        forged_source["manifest"]
    )
    forged_body = {
        key: value for key, value in forged_source.items() if key != "evidence_root"
    }
    forged_source["evidence_root"] = chash(forged_body)
    forged_fields = portable_fields(deep["verified_predecessor"])
    forged_fields["source_authority_context_evidence"] = forged_source
    with pytest.raises(HistoryChainMismatch, match="relocation is not root-only"):
        ConceptricStore.prepare_portable_authority_checkpoint(
            recovered,
            expected_predecessor=deep["verified_predecessor"],
            authority_context=target_context,
            expected_store_role="live-runtime-fabric",
            source_snapshot_id="sha256:" + ("1" * 64),
            source_receipt_sha256="sha256:" + ("2" * 64),
            source_ledger_sha256=source_ledger_sha256,
            source_cursor=1,
            source_head_event_id=stored.event.event_id,
            source_head_record_digest=stored.record_digest,
            **forged_fields,
        )
    assert (recovered / "conceptric.sqlite3").read_bytes() == ledger_before_refusal
    assert ConceptricStore.read_portable_authority_adoption(
        recovered, expected_store_role="live-runtime-fabric"
    ) is None

    adopted = ConceptricStore.prepare_portable_authority_checkpoint(
        recovered,
        expected_predecessor=deep["verified_predecessor"],
        authority_context=target_context,
        expected_store_role="live-runtime-fabric",
        source_snapshot_id="sha256:" + ("1" * 64),
        source_receipt_sha256="sha256:" + ("2" * 64),
        source_ledger_sha256=source_ledger_sha256,
        source_cursor=1,
        source_head_event_id=stored.event.event_id,
        source_head_record_digest=stored.record_digest,
        **portable_fields(deep["verified_predecessor"]),
    )
    assert adopted["idempotent"] is False
    assert adopted["event_append"] is False
    assert ConceptricStore.read_drift_token(recovered) == before
    sealed = ConceptricStore.seal_portable_authority_adoption(
        recovered,
        expected_store_role="live-runtime-fabric",
        expected_source_snapshot_id=adopted["source_snapshot_id"],
        expected_checkpoint_digest=adopted["target_checkpoint_digest"],
        expected_grant_root=adopted["grant_root"],
        target_canonical_root=recovered,
    )
    assert sealed["event_count"] == 1
    fast = ConceptricStore.read_authority_checkpoint(
        recovered, expected_context=target_context
    )
    parity = ConceptricStore.verify_authority_checkpoint_deep(
        recovered,
        expected_context=target_context,
        expected_store_role="live-runtime-fabric",
    )
    assert fast["status"] == "CURRENT"
    assert fast["checkpoint_digest"] == adopted["target_checkpoint_digest"]
    assert parity["status"] == "EXACT"
    assert parity["fast_deep_equal"] is True

    retry = ConceptricStore.prepare_portable_authority_checkpoint(
        recovered,
        expected_predecessor=deep["verified_predecessor"],
        authority_context=target_context,
        expected_store_role="live-runtime-fabric",
        source_snapshot_id="sha256:" + ("1" * 64),
        source_receipt_sha256="sha256:" + ("2" * 64),
        source_ledger_sha256=source_ledger_sha256,
        source_cursor=1,
        source_head_event_id=stored.event.event_id,
        source_head_record_digest=stored.record_digest,
        **portable_fields(deep["verified_predecessor"]),
    )
    assert retry["idempotent"] is True
    assert retry["ledger_checkpoint_write"] is False

    cold_writer = ConceptricStore(
        recovered,
        expected_store_role="live-runtime-fabric",
        authority_context=target_context,
    )
    appended = cold_writer.append(_sew())
    assert appended.sequence == 2


@pytest.mark.parametrize(
    "mutation",
    (
        "files",
        "python",
        "version",
        "platform",
        "dirty",
        "role",
        "schema",
        "environment-root",
        "evidence-root",
    ),
)
def test_portable_authority_context_relocation_allows_only_canonical_root(
    tmp_path: Path,
    mutation: str,
) -> None:
    source = ConceptricStore.authority_context_evidence(
        tmp_path / "source",
        store_role="live-runtime-fabric",
    )
    destination = tmp_path / "destination"
    target = ConceptricStore.authority_context_evidence(
        destination,
        store_role="live-runtime-fabric",
    )
    exact = ConceptricStore._verify_portable_authority_context_relocation(
        source,
        target,
        destination_root=destination,
    )
    assert exact["source_root"] != exact["destination_root"]
    assert exact["changed_fields"] == [
        "manifest.store.root",
        "roots.environment_root",
        "evidence_root",
    ]

    forged = json.loads(json.dumps(source))
    if mutation == "files":
        first = next(iter(forged["manifest"]["files"]))
        forged["manifest"]["files"][first] = "sha256:" + ("f" * 64)
    elif mutation == "python":
        forged["manifest"]["runtime"]["python"] = "ForeignPython"
    elif mutation == "version":
        forged["manifest"]["runtime"]["version"] = [99, 1, 0]
    elif mutation == "platform":
        forged["manifest"]["runtime"]["platform"] = "ForeignOS"
    elif mutation == "dirty":
        forged["dirty"]["porcelain_v1_z_sha256"] = "sha256:" + ("d" * 64)
    elif mutation == "role":
        forged["manifest"]["store"]["role"] = "foreign-role"
    elif mutation == "schema":
        forged["manifest"]["store"]["ledger_schema"] = "foreign-schema"

    if mutation not in {"environment-root", "evidence-root"}:
        forged["roots"] = {
            "implementation_digest": chash(
                {
                    "schema_version": "atlas.authority-implementation/1",
                    "files": forged["manifest"]["files"],
                }
            ),
            "environment_root": chash(forged["manifest"]),
            "dirty_paths_root": chash(forged["dirty"]),
        }
    elif mutation == "environment-root":
        forged["roots"]["environment_root"] = "sha256:" + ("e" * 64)
    forged_body = {
        key: value for key, value in forged.items() if key != "evidence_root"
    }
    forged["evidence_root"] = (
        "sha256:" + ("0" * 64)
        if mutation == "evidence-root"
        else chash(forged_body)
    )

    with pytest.raises((StoreError, HistoryChainMismatch)):
        ConceptricStore._verify_portable_authority_context_relocation(
            forged,
            target,
            destination_root=destination,
        )


def test_writer_refreshes_stale_context_checkpoint_and_live_git_remains_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConceptricStore(tmp_path)
    store.append(_wake())
    before = ConceptricStore.read_drift_token(tmp_path)
    current = dict(store._authority_context)
    with store._connect() as ledger:
        row = ledger.execute(
            "SELECT checkpoint_json, checkpoint_digest FROM authority_checkpoint "
            "WHERE singleton = 1"
        ).fetchone()
        original_checkpoint = (
            str(row["checkpoint_json"]),
            str(row["checkpoint_digest"]),
        )
        stale = json.loads(original_checkpoint[0])
        stale["implementation_digest"] = "sha256:" + ("b" * 64)
        ledger.execute(
            "UPDATE authority_checkpoint SET checkpoint_json = ?, checkpoint_digest = ? "
            "WHERE singleton = 1",
            (canonical_json(stale), chash(stale)),
        )
        ledger.commit()
    store.append(_sew())
    refreshed = ConceptricStore.read_authority_checkpoint(tmp_path)
    assert refreshed["status"] == "CURRENT"
    assert refreshed["checkpoint"]["implementation_digest"] == current["implementation_digest"]
    assert ConceptricStore.read_drift_token(tmp_path)["head_record_digest"] != before["head_record_digest"]

    def unavailable(*args, **kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr("atlas.store.subprocess.run", unavailable)
    with pytest.raises(StoreError, match="Git state is unavailable"):
        ConceptricStore.authority_context_manifest(
            tmp_path, store_role="live-runtime-fabric"
        )


def test_authority_checkpoint_crash_boundaries_keep_canonical_authority(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path)
    store.append(_wake())
    before = ConceptricStore.read_authority_checkpoint(tmp_path)

    orphan = _unrelated(999)
    store.hive.put(canonical_json(orphan.to_dict()).encode())
    after_orphan = ConceptricStore.read_authority_checkpoint(tmp_path)
    assert after_orphan["checkpoint_digest"] == before["checkpoint_digest"]

    with store._connect_projection() as projection:
        projection.execute(
            "UPDATE meta SET value = ? WHERE key = 'authoritative_head_digest'",
            ("sha256:" + ("0" * 64),),
        )
        projection.commit()
    after_projection_crash = ConceptricStore.read_authority_checkpoint(tmp_path)
    assert after_projection_crash["status"] == "CURRENT"
    assert after_projection_crash["checkpoint_digest"] == before["checkpoint_digest"]


def test_object_kind_frontier_is_keyed_verified_and_cas_scoped(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path)
    store.append(_wake())
    initial = store.read_object_kind_frontier(kind="laplace.test-annotation/1")
    assert initial["rows"] == []
    assert initial["read_metrics"] == {
        "projection_rows_loaded": 0,
        "declaration_rows_loaded": 0,
        "global_history_replayed": False,
    }

    store.append(_unrelated(1))
    after_unrelated = store.read_object_kind_frontier(kind="laplace.test-annotation/1")
    assert after_unrelated["frontier_root"] == initial["frontier_root"]

    before_refusals = ConceptricStore.read_drift_token(tmp_path)
    with pytest.raises(StoreError, match="OBJECT declarations only"):
        store.append_many_if_object_kind_frontier(
            (_unrelated(2),),
            kind="laplace.test-annotation/1",
            expected_frontier_root=initial["frontier_root"],
        )
    with pytest.raises(StoreError, match="does not match its frontier"):
        store.append_many_if_object_kind_frontier(
            (
                _object_event(
                    "annotation-event:wrong-kind",
                    kind="laplace.other-object/1",
                    content="sha256:" + ("f" * 64),
                ),
            ),
            kind="laplace.test-annotation/1",
            expected_frontier_root=initial["frontier_root"],
        )
    assert ConceptricStore.read_drift_token(tmp_path) == before_refusals

    stored = store.append_many_if_object_kind_frontier(
        (
            _object_event(
                "annotation-event:first",
                kind="laplace.test-annotation/1",
                content="sha256:" + ("1" * 64),
            ),
        ),
        kind="laplace.test-annotation/1",
        expected_frontier_root=initial["frontier_root"],
    )
    assert len(stored) == 1
    current = store.read_object_kind_frontier(kind="laplace.test-annotation/1")
    assert [row["object"]["object_id"] for row in current["rows"]] == [
        "annotation-event:first"
    ]
    assert current["read_metrics"]["global_history_replayed"] is False

    before = ConceptricStore.read_drift_token(tmp_path)
    with pytest.raises(HistoryChainMismatch, match="frontier moved"):
        store.append_many_if_object_kind_frontier(
            (
                _object_event(
                    "annotation-event:stale",
                    kind="laplace.test-annotation/1",
                    content="sha256:" + ("2" * 64),
                ),
            ),
            kind="laplace.test-annotation/1",
            expected_frontier_root=initial["frontier_root"],
        )
    assert ConceptricStore.read_drift_token(tmp_path) == before


def test_object_kind_frontier_refuses_corrupt_projection_row(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path)
    store.append(_wake())
    store.append_many_if_object_kind_frontier(
        (
            _object_event(
                "annotation-event:first",
                kind="laplace.test-annotation/1",
                content="sha256:" + ("1" * 64),
            ),
        ),
        kind="laplace.test-annotation/1",
        expected_frontier_root=store.read_object_kind_frontier(
            kind="laplace.test-annotation/1"
        )["frontier_root"],
    )
    with store._connect_projection() as projection:
        projection.execute(
            "UPDATE objects SET object_json = ? WHERE object_id = ?",
            ('{"not":"a conceptric object"}', "annotation-event:first"),
        )
        projection.commit()
    with pytest.raises(HistoryChainMismatch, match="row is unreadable"):
        ConceptricStore(tmp_path, read_only=True).read_object_kind_frontier(
            kind="laplace.test-annotation/1"
        )
