from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from atlas.errors import StateTransitionRefused
from atlas.history import EventKind

from laplace.representation import atlas_bridge
from laplace.engine import descent, sources


def _bootstrap_descent_atlas() -> None:
    atlas_bridge.lifecycle(
        action="cold-wake",
        receipt_id="cold:typed-descent-test",
        provider="codex",
        model="gpt-5",
    )
    atlas_bridge.seat_transition(
        seat_id="codex-seat",
        role="provider",
        action="found",
        charter_ref="charter:provider",
        holder_ref="holder:codex-seat:test",
        provider="codex",
        model="gpt-5",
    )
    atlas_bridge.select_context(
        assumption="typed descent is observed without changing its source",
        fibre="typed-descent-tests",
        provider="codex",
        model="gpt-5",
        confidence=1.0,
    )


def test_ledger_row_resolves_exact_registered_identity_not_semantic_neighbour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "rows.jsonl"
    rows = [
        {"id": "WO-exact", "what": "the actual contract"},
        {"id": "WO-neighbour", "what": "WO-exact appears only as nearby prose"},
    ]
    raw = b"".join(json.dumps(row, sort_keys=True).encode("utf-8") + b"\n" for row in rows)
    store.write_bytes(raw)
    monkeypatch.setitem(
        sources.SOURCES,
        "descent_test",
        {
            "path": "rows.jsonl",
            "id_field": "id",
            "ts_field": None,
            "kind_field": None,
            "staleness": 1,
            "facets": [],
            "columns": ["id", "what"],
            "label": "test",
        },
    )
    monkeypatch.setattr(sources, "_repo_root", lambda: tmp_path)

    got = descent.descend(kind="ledger-row", reference="WO-exact", source="descent_test")

    first = json.dumps(rows[0], sort_keys=True).encode("utf-8") + b"\n"
    assert got["value"] == rows[0]
    assert got["content_handle"] == "sha256:" + hashlib.sha256(first).hexdigest()
    assert got["handle"] == "WO-exact"
    assert got["content"] == first.decode("utf-8")
    assert got["content_status"] == "COMPLETE"
    assert got["content_truncated"] is False
    assert got["content_omitted"] == 0
    assert got["provenance"]["byte_offset"] == 0
    assert got["semantic_state_claim"].startswith("none")


def test_blueprint_exact_resolution_serves_banked_source_and_reports_code_drift(
    tmp_path: Path,
) -> None:
    design = tmp_path / "design.md"
    design.write_text("# clause\nbody\n", encoding="utf-8")
    implementation = tmp_path / "impl.py"
    implementation.write_text("VALUE = 1\n", encoding="utf-8")
    source_bytes = design.read_bytes()
    exact = source_bytes
    generation = SimpleNamespace(
        clauses=(
            {
                "logical_id": "design:test::clause::0",
                "subject_id": "design-subject:1",
                "subject_handle": "sha256:" + "1" * 64,
                "object_id": "design-clause:1",
                "content_handle": "sha256:" + "2" * 64,
                "exact_byte_hash": atlas_bridge.hash_bytes(exact),
                "source_path": "design.md",
                "source_hash": atlas_bridge.hash_bytes(source_bytes),
                "start": 0,
                "end": len(source_bytes),
            },
        ),
        bindings=(
            {
                "clause_logical_id": "design:test::clause::0",
                "implementation_path": "impl.py",
                "implementation_hash": "sha256:" + "f" * 64,
            },
        ),
    )
    clause = generation.clauses[0]
    item = {
        "object_id": clause["object_id"],
        "kind": "source-leaf",
        "content_handle": clause["content_handle"],
        "attributes": {
            "logical_id": clause["logical_id"],
            "subject_handle": clause["subject_handle"],
            "exact_byte_hash": clause["exact_byte_hash"],
            "text": exact.decode("utf-8"),
        },
    }

    def resolve(reference="design-clause:1"):
        return atlas_bridge._resolve_blueprint_clause(
            generation, reference, object_reader=lambda _object_id: item, repo_root=tmp_path,
        )

    got = resolve()
    assert got["text"] == "# clause\nbody\n"
    assert got["implements"][0]["implementation_current"] is False

    design.write_text("# clause\nchanged\n", encoding="utf-8")
    assert resolve()["text"] == exact.decode("utf-8")
    design.unlink()
    assert resolve()["text"] == exact.decode("utf-8")
    assert resolve()["content_basis"] == "completed-generation-banked-bytes"
    with pytest.raises(StateTransitionRefused, match="exactly one"):
        resolve("design-clause:absent")
    item["content_handle"] = "sha256:" + "9" * 64
    with pytest.raises(StateTransitionRefused, match="contradicts"):
        resolve()
    item["content_handle"] = clause["content_handle"]
    item["attributes"]["text"] = "corrupt banked bytes"
    with pytest.raises(StateTransitionRefused, match="exact byte span"):
        resolve()


def test_blueprint_typed_descent_hoists_advisory_freshness_and_keeps_banked_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = {
        "generation_id": "generation:1",
        "clause": {
            "content_handle": "sha256:" + hashlib.sha256(b"exact").hexdigest(),
            "source_path": "design.md",
            "source_hash": "sha256:" + "3" * 64,
            "start": 1,
            "end": 2,
        },
        "text": "exact",
        "generation_current": True,
        "moved_source_roots": [],
        "storage_access": "sqlite mode=ro/query_only; bounded shared flock",
    }
    monkeypatch.setattr(atlas_bridge, "blueprint_descent", lambda **_kwargs: dict(base))
    fresh = descent.descend(kind="blueprint", reference="design-clause:1")
    assert fresh["generation_current"] is True and fresh["moved_source_roots"] == []
    assert fresh["moved_source_root_count"] == 0
    assert fresh["storage_access"].startswith("sqlite mode=ro")

    moved = [{"path": "src/live.py", "expected": "sha256:old", "actual": "sha256:new"}]
    monkeypatch.setattr(
        atlas_bridge,
        "blueprint_descent",
        lambda **_kwargs: {**base, "generation_current": False, "moved_source_roots": moved},
    )
    stored = descent.descend(kind="blueprint", reference="design-clause:1")
    assert stored["content"] == fresh["content"] == "exact"
    assert stored["generation_current"] is False
    assert stored["source_currency"] == "MOVED"
    assert stored["moved_source_roots"] == moved
    assert stored["storage_access"].startswith("sqlite mode=ro")
    assert stored["transition_claim"] == "none"


@pytest.mark.parametrize("index_state", ["present", "absent", "damaged"])
@pytest.mark.parametrize("remove_source", [True, False])
def test_blueprint_banked_read_survives_source_movement_without_store_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    index_state: str, remove_source: bool,
) -> None:
    from atlas.blueprint import pour_blueprint
    from atlas.store import ConceptricStore
    from test_blueprint import fixtures, write_fixture

    documents = write_fixture(tmp_path)
    encoder, contract, metadata, bindings = fixtures(tmp_path)
    root = tmp_path / "store"
    store = ConceptricStore(root, expected_store_role="blueprint-generation")
    generation = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata,
    )
    clause = next(row for row in generation.clauses if row["source_path"] == "design/atomic.md")
    source = tmp_path / clause["source_path"]
    expected = source.read_bytes()[clause["start"]:clause["end"]]
    if remove_source:
        source.unlink()
    else:
        source.write_text("# A later design\nThe banked generation must not change.\n")
    if index_state == "absent":
        store.projection_path.unlink()
    elif index_state == "damaged":
        with sqlite3.connect(store.projection_path) as connection:
            value = json.loads(connection.execute(
                "SELECT object_json FROM objects WHERE object_id = ?", (clause["object_id"],),
            ).fetchone()[0])
            value["attributes"]["text"] = "The sidecar must not substitute these bytes."
            connection.execute(
                "UPDATE objects SET object_json = ? WHERE object_id = ?",
                (json.dumps(value, sort_keys=True, separators=(",", ":")), clause["object_id"]),
            )

    manifest = tmp_path / "blueprint_manifest.json"
    raw = {"store": "store", "dataset_roots": {"engine": "."}}
    manifest.write_text(json.dumps(raw))
    monkeypatch.setattr(atlas_bridge, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(atlas_bridge, "_blueprint_manifest", lambda: (manifest, raw))
    before_head = ConceptricStore.read_drift_token(root)
    canonical = [store.path, *sorted(store.hive_root.glob("*/*.zlib"))]
    if store.projection_path.is_file():
        canonical.append(store.projection_path)
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in canonical}
    before_paths = set(root.rglob("*"))

    if index_state == "damaged":
        with pytest.raises(atlas_bridge.HistoryChainMismatch):
            descent.descend(kind="blueprint", reference=clause["logical_id"])
    else:
        result = descent.descend(kind="blueprint", reference=clause["logical_id"])
        assert result["content"].encode("utf-8") == expected
        assert result["generation_current"] is False
        assert result["source_currency"] == "MOVED"
        assert result["provenance"]["generation_id"] == generation.generation_id
        assert result["value"]["read_metrics"]["generation_selection"] == "verified-event-history-scan"
        assert result["value"]["read_metrics"]["global_history_replayed"] is (index_state == "absent")
    assert ConceptricStore.read_drift_token(root) == before_head
    assert store.projection_path.is_file() is (index_state != "absent")
    assert set(root.rglob("*")) == before_paths
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in canonical} == before


def test_unknown_or_ambiguous_reference_type_refuses() -> None:
    with pytest.raises(descent.DescentRefused, match="unknown descent kind"):
        descent.descend(kind="semantic-ish", reference="sha256:" + "0" * 64)
    with pytest.raises(descent.DescentRefused, match="must start"):
        descent.descend(kind="fabric-message", reference="sha256:" + "0" * 64)


def test_bounded_descent_names_every_omitted_byte_and_continues_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = {"id": "WO-windowed", "what": "αβγδ" * 90}
    raw = json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
    (tmp_path / "rows.jsonl").write_bytes(raw)
    monkeypatch.setitem(
        sources.SOURCES,
        "windowed_descent",
        {
            "path": "rows.jsonl",
            "id_field": "id",
            "ts_field": None,
            "kind_field": None,
            "staleness": 1,
            "facets": [],
            "columns": ["id", "what"],
            "label": "test",
        },
    )
    monkeypatch.setattr(sources, "_repo_root", lambda: tmp_path)

    offset = 0
    recovered = bytearray()
    first = None
    while True:
        got = descent.descend(
            kind="ledger-row",
            reference="WO-windowed",
            source="windowed_descent",
            content_budget=65,
            content_offset=offset,
        )
        first = first or got
        recovered.extend(got["content"].encode("utf-8"))
        if got["content_next_offset"] is None:
            break
        assert got["content_next_offset"] > offset
        offset = got["content_next_offset"]

    assert first is not None
    assert first["content_status"] == "TRUNCATED"
    assert first["content_truncated"] is True
    assert first["content_omitted"] == len(raw) - len(first["content"].encode("utf-8"))
    assert first["content_handle"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert first["value_omitted"] is True and "value" not in first
    assert bytes(recovered) == raw


def test_zero_content_budget_is_a_typed_residue_not_handle_only_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = {"id": "WO-budget", "what": "content exists"}
    raw = json.dumps(row).encode("utf-8") + b"\n"
    (tmp_path / "rows.jsonl").write_bytes(raw)
    monkeypatch.setitem(
        sources.SOURCES,
        "budget_descent",
        {
            "path": "rows.jsonl",
            "id_field": "id",
            "ts_field": None,
            "kind_field": None,
            "staleness": 1,
            "facets": [],
            "columns": ["id", "what"],
            "label": "test",
        },
    )
    monkeypatch.setattr(sources, "_repo_root", lambda: tmp_path)

    got = descent.descend(
        kind="ledger-row",
        reference="WO-budget",
        source="budget_descent",
        content_budget=0,
    )

    assert got["content"] is None
    assert got["content_status"] == "BUDGET"
    assert got["content_residue"]["code"] == "BUDGET"
    assert got["content_omitted"] == len(raw)
    assert got["content_handle"] == "sha256:" + hashlib.sha256(raw).hexdigest()


def test_binary_carriage_charges_base64_expansion_to_the_response_budget() -> None:
    raw = bytes(range(31))
    offset = 0
    recovered = bytearray()
    while True:
        got = descent.bounded_content(
            handle="binary:test",
            content=raw,
            media_type="application/octet-stream",
            budget=9,
            offset=offset,
        )
        assert len(got["content"]) <= 9
        recovered.extend(base64.b64decode(got["content"]))
        if got["content_next_offset"] is None:
            break
        assert got["content_next_offset"] > offset
        offset = got["content_next_offset"]

    assert bytes(recovered) == raw

    unaffordable = descent.bounded_content(
        handle="binary:test",
        content=raw,
        media_type="application/octet-stream",
        budget=3,
    )
    assert unaffordable["content_status"] == "BUDGET"
    assert unaffordable["content_residue"]["required_bytes"] == 4


def test_terminal_partial_window_is_final_not_truncated() -> None:
    got = descent.bounded_content(
        handle="text:final-window",
        content=b"abcdef",
        budget=2,
        offset=4,
    )

    assert got["content"] == "ef"
    assert got["content_status"] == "FINAL"
    assert got["content_truncated"] is False
    assert got["content_next_offset"] is None
    assert got["content_omitted_before"] == 4
    assert got["content_omitted_after"] == 0


def test_bounded_content_refuses_a_handle_that_does_not_name_the_bytes() -> None:
    raw = b"the exact content"
    with pytest.raises(descent.DescentRefused, match="does not name") as caught:
        descent.bounded_content(
            handle="content:test",
            content=raw,
            content_handle="sha256:" + "0" * 64,
        )

    residue = caught.value.details["residue"]
    assert residue["code"] == "CONTENT_HANDLE_MISMATCH"
    assert residue["calculated_handle"] == "sha256:" + hashlib.sha256(raw).hexdigest()


def test_empty_binary_content_keeps_binary_encoding() -> None:
    got = descent.bounded_content(
        handle="binary:empty",
        content=b"",
        media_type="application/octet-stream",
        budget=0,
    )

    assert got["content_status"] == "COMPLETE"
    assert got["content"] == ""
    assert got["content_encoding"] == "base64"


def test_exact_descent_banks_causal_move_and_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bootstrap_descent_atlas()
    row = {"id": "WO-observed", "what": "exact observed content"}
    raw = json.dumps(row, sort_keys=True).encode("utf-8") + b"\n"
    (tmp_path / "rows.jsonl").write_bytes(raw)
    monkeypatch.setitem(
        sources.SOURCES,
        "observed_descent",
        {
            "path": "rows.jsonl",
            "id_field": "id",
            "ts_field": None,
            "kind_field": None,
            "staleness": 1,
            "facets": [],
            "columns": ["id", "what"],
            "label": "test",
        },
    )
    monkeypatch.setattr(sources, "_repo_root", lambda: tmp_path)

    result = descent.descend(
        kind="ledger-row",
        reference="WO-observed",
        source="observed_descent",
        goal="prove the exact row was reconstructed",
        seat_id="codex-seat",
        provider="codex",
        model="gpt-5",
        correlation_id="trace:observed-descent",
        record_telemetry=True,
    )

    trace = result["telemetry"]
    assert trace["status"] == "MATERIALIZED"
    assert trace["correlation_id"] == "trace:observed-descent"
    assert trace["duration_ms"] >= 0
    state = atlas_bridge._read_store().current_state()
    assert trace["movement_id"] in state.movements
    assert any(
        item.materialization_id == trace["materialization_id"]
        for item in state.materializations.values()
    )
    move, materialization = atlas_bridge._read_store().events()[-2:]
    assert move.kind == EventKind.MOVE
    assert materialization.kind == EventKind.MATERIALIZATION
    assert move.correlation_id == materialization.correlation_id
    assert materialization.causation_ids == (move.event_id,)
    assert materialization.payload["coverage"] == 1.0


def test_typed_refusal_materializes_exceeds_bound_residual() -> None:
    _bootstrap_descent_atlas()

    with pytest.raises(descent.DescentRefused, match="must start") as caught:
        descent.descend(
            kind="fabric-message",
            reference="sha256:" + "0" * 64,
            goal="observe an exact typed refusal",
            seat_id="codex-seat",
            provider="codex",
            model="gpt-5",
            correlation_id="trace:refused-descent",
            record_telemetry=True,
        )

    trace = caught.value.details["telemetry"]
    assert trace["status"] == "REFUSED"
    move, materialization = atlas_bridge._read_store().events()[-2:]
    assert move.kind == EventKind.MOVE
    assert materialization.kind == EventKind.MATERIALIZATION
    assert materialization.causation_ids == (move.event_id,)
    assert materialization.payload["coverage"] == 0.0
    assert materialization.payload["residual"]["status"] == "exceeds_bound"


def test_exact_read_survives_but_names_unavailable_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = {"id": "WO-no-context", "what": "the source read still succeeds"}
    (tmp_path / "rows.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setitem(
        sources.SOURCES,
        "unobserved_descent",
        {
            "path": "rows.jsonl",
            "id_field": "id",
            "ts_field": None,
            "kind_field": None,
            "staleness": 1,
            "facets": [],
            "columns": ["id", "what"],
            "label": "test",
        },
    )
    monkeypatch.setattr(sources, "_repo_root", lambda: tmp_path)

    result = descent.descend(
        kind="ledger-row", reference="WO-no-context", source="unobserved_descent", record_telemetry=True
    )

    assert result["value"] == row
    assert result["telemetry"]["status"] == "UNAVAILABLE"
    assert "selected assumption fibre" in result["telemetry"]["error"]


def test_nontelemetric_typed_descent_cannot_move_the_atlas_head() -> None:
    _bootstrap_descent_atlas()
    before = atlas_bridge.drift_token()

    result = descent.descend(
        kind="repository-file",
        reference="HANDOFF.md",
        goal="orient without mutating authority",
        content_budget=256,
    )

    assert result["content_status"] == "TRUNCATED"
    assert result["read_only"] is True
    assert result["authority_write"] == "none"
    assert result["transition_claim"] == "none"
    assert result["telemetry"] == {
        "schema_version": "laplace.engine.descent-trace/1",
        "status": "NOT_REQUESTED",
        "authority_write": "none",
    }
    assert atlas_bridge.drift_token() == before
