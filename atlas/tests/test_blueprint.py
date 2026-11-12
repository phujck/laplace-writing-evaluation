from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from atlas.blueprint import (
    DesignDocument,
    EvidenceFinding,
    ImplementationBinding,
    current_blueprint_generation,
    pour_blueprint,
    reconstruct_blueprint,
)
from atlas.encoders.base import EncoderRuntimeEvidence, EncoderSpec, unit
from atlas.encoders.deterministic import SyntheticEncoder
from atlas.errors import StateTransitionRefused
from atlas.history import GradeAxisContract, ProducerRef, SeatRole, SourceRef
from atlas.ids import hash_bytes
from atlas.routing import RawCosineRouter
from atlas.runtime import collect_runtime_receipt
from atlas.spectral_pour import PourLeaf, PourMetadata, SpectralPourContract
from atlas.store import ConceptricStore


def write_fixture(root: Path) -> tuple[DesignDocument, ...]:
    texts = {
        "design/atomic.md": "# Alpha atomic banking\n\nalpha one canonical atomic banking path.\n",
        "design/spectral.md": "# Beta spectral margin\n\nbeta persist the frame and spectral margin at pour.\n",
        "design/mutation.md": "# Gamma dirty mutation\n\ngamma repair dirty ancestry without moving siblings.\n",
        "design/fidelity.md": "# Delta fidelity\n\ndelta exact source custody and proof links survive scale.\n",
    }
    for path, text in texts.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (root / "impl").mkdir()
    (root / "impl/store.py").write_text("def append_many(): pass\n", encoding="utf-8")
    (root / "impl/test_store.py").write_text("def test_atomic(): pass\n", encoding="utf-8")
    (root / "impl/spectral.py").write_text("def persist_frame(): pass\n", encoding="utf-8")
    return tuple(DesignDocument(path, "s1-design") for path in texts)


def fixtures(root: Path):
    encoder = SyntheticEncoder()
    contract = SpectralPourContract(
        "the S1 blueprint is the current design corpus",
        "s1-blueprint-test",
        GradeAxisContract(
            "axis-contract:s1-blueprint-test/1",
            "source-detail",
            ("cluster", "leaf"),
        ),
        "test-blueprint-design/1",
        encoder.spec,
        encoder.encoder_id,
        2,
        1,
        0.8,
    )
    source = SourceRef(
        "test:blueprint",
        "sha256:" + "a" * 64,
        "test://blueprint",
    )
    metadata = PourMetadata(
        "2026-08-24T22:00:00Z",
        SeatRole.EGO,
        SeatRole.EGO,
        "blueprint-test",
        (source,),
        collect_runtime_receipt(root, observed_at="2026-08-24T22:00:00Z"),
        ProducerRef("test-provider", "deterministic", "blueprint-test"),
        EncoderRuntimeEvidence(
            encoder.spec.spec_id,
            "sha256:" + "7" * 64,
            ("deterministic-python",),
            encoder.spec.determinism_metric,
            0.0,
            encoder.spec.determinism_tolerance,
        ),
    )
    bindings = (
        ImplementationBinding(
            "canonical atomic banking path",
            "impl/store.py",
            "python-module",
            "conjecture",
            ("test:atomic-packet",),
            "codex-seat",
            None,
            "atomic append and rollback path only",
        ),
        ImplementationBinding(
            "frame and spectral margin",
            "impl/spectral.py",
            "python-module",
            "planted-proved",
            ("test:spectral-frame",),
            "codex-seat",
            "claude-seat",
        ),
    )
    return encoder, contract, metadata, bindings


def test_blueprint_is_current_only_with_spectral_route_and_implementation_joins(
    tmp_path: Path,
) -> None:
    documents = write_fixture(tmp_path)
    encoder, contract, metadata, bindings = fixtures(tmp_path)
    store = ConceptricStore(tmp_path / "store")

    generation = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata
    )
    current = current_blueprint_generation(store)
    state = store.replay()

    assert current == generation
    assert current.pour_handle
    assert len(current.clauses) == 4
    assert len(current.clusters) == 2
    assert {item["proof_state"] for item in current.bindings} == {
        "conjecture",
        "planted-proved",
    }
    assert {
        edge.relation for edge in state.graph_edges.values() if edge.relation == "implements"
    } == {"implements"}


def test_cold_spectral_reconstruction_resolves_exact_clause_and_implementation(
    tmp_path: Path,
) -> None:
    documents = write_fixture(tmp_path)
    encoder, contract, metadata, bindings = fixtures(tmp_path)
    root = tmp_path / "store"
    store = ConceptricStore(root)
    generation = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata
    )

    cold = ConceptricStore(root)
    result = reconstruct_blueprint(
        cold,
        tmp_path,
        "alpha canonical atomic banking implementation",
        encoder,
        metadata,
        top_k=2,
        beam=1,
    )

    assert result.generation_id == generation.generation_id
    assert result.cache_hit is False
    assert len(result.traversed_cluster_ids) == 1
    assert len(result.rejected_cluster_ids) == 1
    assert result.results[0]["source_path"] == "design/atomic.md"
    assert result.results[0]["subject_handle"].startswith("sha256:")
    assert result.results[0]["subject_id"].startswith("design-subject:")
    assert result.results[0]["version_edge_id"].startswith("edge:version-of:")
    assert result.results[0]["implements"][0]["implementation_path"] == "impl/store.py"
    assert result.results[0]["implements"][0]["proof_state"] == "conjecture"
    assert result.results[0]["implements"][0]["implementation_scope"] == \
        "atomic append and rollback path only"
    source = (tmp_path / result.results[0]["source_path"]).read_bytes()
    assert source[result.results[0]["start"]:result.results[0]["end"]].decode() == \
        result.results[0]["text"]

    reused = reconstruct_blueprint(
        cold,
        tmp_path,
        "alpha canonical atomic banking implementation",
        encoder,
        metadata,
        top_k=2,
        beam=1,
    )
    assert reused.cache_hit is True
    assert reused.materialization_id == result.materialization_id


def test_current_reconstruction_excludes_historical_implementation_bindings(
    tmp_path: Path,
) -> None:
    documents = write_fixture(tmp_path)
    encoder, contract, metadata, bindings = fixtures(tmp_path)
    store = ConceptricStore(tmp_path / "store")
    first = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata
    )
    first_binding = next(
        binding for binding in first.bindings
        if binding["implementation_path"] == "impl/store.py"
    )

    (tmp_path / "impl/store.py").write_text(
        "def append_many():\n    return 'current'\n", encoding="utf-8"
    )
    second = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata,
        parent_generation=first.generation_id,
    )
    second_binding = next(
        binding for binding in second.bindings
        if binding["implementation_path"] == "impl/store.py"
    )
    assert second_binding["edge_id"] != first_binding["edge_id"]

    result = reconstruct_blueprint(
        ConceptricStore(store.root),
        tmp_path,
        "alpha canonical atomic banking implementation",
        encoder,
        metadata,
        top_k=2,
        beam=1,
    )
    atomic = next(
        item for item in result.results
        if item["source_path"] == "design/atomic.md"
    )
    assert [item["edge_id"] for item in atomic["implements"]] == [
        second_binding["edge_id"]
    ]
    assert [item["implementation_hash"] for item in atomic["implements"]] == [
        second_binding["implementation_hash"]
    ]


def test_moved_design_serves_banked_text_until_a_new_generation_is_poured(
    tmp_path: Path,
) -> None:
    documents = write_fixture(tmp_path)
    encoder, contract, metadata, bindings = fixtures(tmp_path)
    store = ConceptricStore(tmp_path / "store")
    first = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata
    )
    first_nodes = {item["cluster_id"]: item["node_handle"] for item in first.clusters}

    path = tmp_path / "design/atomic.md"
    path.write_text(
        "# Alpha atomic banking\n\nalpha one canonical atomic banking path with exact replay.\n",
        encoding="utf-8",
    )
    result = reconstruct_blueprint(
        store, tmp_path, "alpha canonical atomic banking implementation", encoder, metadata,
    )
    assert result.source_currency["source_roots"] == "MOVED"
    assert "alpha one canonical atomic banking path." in result.results[0]["text"]

    second = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata,
        parent_generation=first.generation_id,
    )
    assert second.generation_id != first.generation_id
    second_nodes = {item["cluster_id"]: item["node_handle"] for item in second.clusters}
    assert set(first_nodes.values()) & set(second_nodes.values())
    first_clause = next(
        item for item in first.clauses if item["source_path"] == "design/atomic.md"
    )
    second_clause = next(
        item for item in second.clauses if item["source_path"] == "design/atomic.md"
    )
    assert second_clause["subject_handle"] == first_clause["subject_handle"]
    assert second_clause["subject_id"] == first_clause["subject_id"]
    assert second_clause["content_handle"] != first_clause["content_handle"]
    assert second_clause["object_id"] != first_clause["object_id"]
    assert second_clause["version_edge_id"] != first_clause["version_edge_id"]
    repaired = reconstruct_blueprint(
        ConceptricStore(store.root),
        tmp_path,
        "alpha canonical atomic banking exact replay",
        encoder,
        metadata,
    )
    assert repaired.generation_id == second.generation_id
    assert "exact replay" in repaired.results[0]["text"]


def test_unchanged_clause_vector_is_independent_of_sibling_batch_shape(
    tmp_path: Path,
) -> None:
    class BatchSensitiveEncoder:
        encoder_id = SyntheticEncoder.encoder_id
        dim = 3
        max_tokens = 512
        spec = EncoderSpec(
            encoder_id,
            "sha256:" + "1" * 64,
            "sha256:" + "2" * 64,
            "batch-sensitive-test/1",
            dim,
            "l2-unit-except-zero/1",
            "",
            "",
            "exact-component-equality/1",
            0.0,
        )

        def embed(self, texts: list[str]) -> list[list[float]]:
            padding_shape = max(len(text) for text in texts)
            return [unit([float(len(text)), float(padding_shape), 1.0]) for text in texts]

        def query(self, text: str) -> list[float]:
            return self.embed([text])[0]

    documents = write_fixture(tmp_path)
    _encoder, contract, metadata, bindings = fixtures(tmp_path)
    encoder = BatchSensitiveEncoder()
    contract = replace(contract, encoder_spec=encoder.spec)
    metadata = replace(
        metadata,
        encoder_runtime_evidence=EncoderRuntimeEvidence.exact_single_provider(
            encoder.spec,
            "deterministic-python",
            "sha256:" + "6" * 64,
        ),
    )
    store = ConceptricStore(tmp_path / "batch-stable-store")
    first = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata
    )
    unchanged = next(
        clause for clause in first.clauses if clause["source_path"] == "design/atomic.md"
    )
    first_vector = tuple(
        store.replay().graph_objects[unchanged["object_id"]].attributes["vector"]
    )

    (tmp_path / "design/spectral.md").write_text(
        "# Beta spectral margin\n\n"
        "beta persist the frame and spectral margin at pour with a much longer sibling.\n",
        encoding="utf-8",
    )
    second = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata,
        parent_generation=first.generation_id,
    )
    still_unchanged = next(
        clause for clause in second.clauses if clause["source_path"] == "design/atomic.md"
    )

    assert still_unchanged["object_id"] == unchanged["object_id"]
    assert tuple(
        store.replay().graph_objects[still_unchanged["object_id"]].attributes["vector"]
    ) == first_vector


def test_moved_implementation_warns_and_serves_banked_join(tmp_path: Path) -> None:
    documents = write_fixture(tmp_path)
    encoder, contract, metadata, bindings = fixtures(tmp_path)
    store = ConceptricStore(tmp_path / "store")
    pour_blueprint(store, tmp_path, documents, bindings, encoder, contract, metadata)

    (tmp_path / "impl/store.py").write_text(
        "def append_many(): return 'moved'\n", encoding="utf-8"
    )

    result = reconstruct_blueprint(
        store, tmp_path, "alpha canonical atomic banking implementation", encoder, metadata,
    )
    assert result.source_currency["source_roots"] == "MOVED"
    assert "alpha one canonical atomic banking path." in result.results[0]["text"]


def test_moved_manifest_or_path_backed_evidence_warns_on_read(
    tmp_path: Path,
) -> None:
    documents = write_fixture(tmp_path)
    encoder, contract, metadata, _bindings = fixtures(tmp_path)
    manifest = tmp_path / "manifest.json"
    evidence = tmp_path / "evidence/receipt.json"
    evidence.parent.mkdir(parents=True)
    manifest.write_text('{"version": 1}\n', encoding="utf-8")
    evidence.write_text('{"verdict": "green"}\n', encoding="utf-8")
    metadata = PourMetadata(
        metadata.occurred_at,
        metadata.producer,
        metadata.actor,
        metadata.correlation_id,
        (
            SourceRef(
                "test:manifest",
                hash_bytes(manifest.read_bytes()),
                "manifest.json",
            ),
        ),
        metadata.runtime,
        metadata.producer_ref,
        metadata.encoder_runtime_evidence,
    )
    evidence_digest = hash_bytes(evidence.read_bytes())
    bindings = (
        ImplementationBinding(
            "canonical atomic banking path",
            "impl/store.py",
            "python-module",
            "conjecture",
            (f"evidence/receipt.json#{evidence_digest}",),
            "codex-seat",
            None,
        ),
    )
    store = ConceptricStore(tmp_path / "store")
    generation = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata
    )
    assert generation.source_roots["container://manifest.json"]
    assert generation.source_roots["container://evidence/receipt.json"] == evidence_digest

    manifest.write_text('{"version": 2}\n', encoding="utf-8")
    result = reconstruct_blueprint(store, tmp_path, "atomic banking", encoder, metadata)
    assert result.source_currency["source_roots"] == "MOVED"

    manifest.write_text('{"version": 1}\n', encoding="utf-8")
    evidence.write_text('{"verdict": "red"}\n', encoding="utf-8")
    result = reconstruct_blueprint(store, tmp_path, "atomic banking", encoder, metadata)
    assert result.source_currency["source_roots"] == "MOVED"


def test_operator_proposal_banks_exact_finding_edges_and_exposes_them_on_route(
    tmp_path: Path,
) -> None:
    documents = write_fixture(tmp_path)
    encoder, contract, metadata, _bindings = fixtures(tmp_path)
    report = tmp_path / "evidence/report.md"
    report.parent.mkdir(parents=True)
    report.write_text(
        "# Receipt\n\nDiffusion weighting wins inside the measured window.\n",
        encoding="utf-8",
    )
    finding = EvidenceFinding(
        "diffusion-window",
        "evidence/report.md",
        hash_bytes(report.read_bytes()),
        1,
        3,
        "weighting wins",
        "Diffusion weighting fixes distances in the measured window.",
        "constrains",
        "measured-once",
        ("placement-embedding",),
        "one fixture corpus; necessary evidence, not authority",
        "s1-design",
    )
    bindings = (
        ImplementationBinding(
            "frame and spectral margin",
            "impl/spectral.py",
            "python-module",
            "conjecture",
            ("test:spectral-frame",),
            "codex-seat",
            None,
            "fixture placement",
            ("placement-embedding",),
            (finding.finding_id,),
        ),
    )
    store = ConceptricStore(tmp_path / "store")

    generation = pour_blueprint(
        store,
        tmp_path,
        documents,
        bindings,
        encoder,
        contract,
        metadata,
        findings=(finding,),
    )
    row = generation.findings[0]
    state = store.replay()
    assert generation.source_roots["container://evidence/report.md"] == finding.file_digest
    assert state.graph_objects[row["object_id"]].attributes["start"] == row["start"]
    assert state.graph_objects[row["subject_id"]].attributes["finding_id"] == finding.finding_id
    assert state.graph_edges[row["version_edge_id"]].source_object_id == row["object_id"]
    assert state.graph_edges[row["version_edge_id"]].target_object_id == row["subject_id"]
    assert {
        state.graph_edges[edge_id].relation for edge_id in row["operator_role_edge_ids"]
    } == {"constrains"}
    assert {
        state.graph_edges[edge_id].relation for edge_id in row["derivation_edge_ids"]
    } == {"derives-from-evidence"}

    result = reconstruct_blueprint(
        store, tmp_path, "beta spectral frame placement", encoder, metadata
    )
    implementation = result.results[0]["implements"][0]
    assert implementation["operator_roles"] == ["placement-embedding"]
    assert implementation["required_findings"][0]["finding_id"] == "diffusion-window"

    dependency = tmp_path / "evidence/scissors.py"
    dependency.write_text("print('second evidence version')\n", encoding="utf-8")
    dependency_handle = f"evidence/scissors.py#{hash_bytes(dependency.read_bytes())}"
    revised_finding = replace(finding, dependency_handles=(dependency_handle,))
    revised = pour_blueprint(
        store,
        tmp_path,
        documents,
        bindings,
        encoder,
        contract,
        metadata,
        findings=(revised_finding,),
        parent_generation=generation.generation_id,
    )
    revised_row = revised.findings[0]
    revised_state = store.replay()
    assert revised_row["subject_id"] == row["subject_id"]
    assert revised_row["object_id"] != row["object_id"]
    assert revised_row["version_edge_id"] != row["version_edge_id"]
    assert row["object_id"] in revised_state.graph_objects
    assert revised_row["object_id"] in revised_state.graph_objects
    assert revised_state.graph_edges[revised_row["version_edge_id"]].target_object_id == row[
        "subject_id"
    ]

    class MigratedSyntheticEncoder(SyntheticEncoder):
        spec = replace(
            SyntheticEncoder.spec,
            model_artifact_digest="sha256:" + "9" * 64,
        )

    migrated_encoder = MigratedSyntheticEncoder()
    migrated_contract = replace(contract, encoder_spec=migrated_encoder.spec)
    assert metadata.encoder_runtime_evidence is not None
    migrated_metadata = replace(
        metadata,
        encoder_runtime_evidence=replace(
            metadata.encoder_runtime_evidence,
            encoder_spec_id=migrated_encoder.spec.spec_id,
        ),
    )
    migrated = pour_blueprint(
        store,
        tmp_path,
        documents,
        bindings,
        migrated_encoder,
        migrated_contract,
        migrated_metadata,
        findings=(revised_finding,),
        parent_generation=revised.generation_id,
    )
    assert migrated.generation_id != generation.generation_id
    assert (
        migrated.findings[0]["operator_role_edge_ids"]
        != generation.findings[0]["operator_role_edge_ids"]
    )
    with pytest.raises(StateTransitionRefused, match="encoder specification contradicts"):
        reconstruct_blueprint(store, tmp_path, "spectral frame", encoder, metadata)
    assert reconstruct_blueprint(
        store, tmp_path, "spectral frame", migrated_encoder, migrated_metadata
    ).generation_id == migrated.generation_id


def test_operator_proposal_without_required_findings_is_a_derivation_gap() -> None:
    with pytest.raises(StateTransitionRefused, match="DERIVATION_GAP"):
        ImplementationBinding(
            "frame and spectral margin",
            "impl/spectral.py",
            "python-module",
            "conjecture",
            ("test:spectral-frame",),
            "codex-seat",
            None,
            "fixture placement",
            ("placement-embedding",),
            (),
        )


def test_finding_refuses_malformed_digest_before_repository_resolution() -> None:
    with pytest.raises(StateTransitionRefused, match="canonical sha256"):
        EvidenceFinding(
            "diffusion-window",
            "evidence/report.md",
            "not-a-digest",
            1,
            3,
            "weighting wins",
            "Diffusion weighting fixes distances in the measured window.",
            "constrains",
            "measured-once",
            ("placement-embedding",),
            "one fixture corpus",
            "s1-design",
        )

def test_route_operator_version_changes_materialization_identity(tmp_path: Path) -> None:
    documents = write_fixture(tmp_path)
    encoder, contract, metadata, bindings = fixtures(tmp_path)
    store = ConceptricStore(tmp_path / "store")
    pour_blueprint(store, tmp_path, documents, bindings, encoder, contract, metadata)

    incumbent = reconstruct_blueprint(
        store, tmp_path, "alpha atomic banking", encoder, metadata
    )
    candidate_operator = RawCosineRouter(operator_version="raw-cosine-router/candidate-2")
    candidate = reconstruct_blueprint(
        store,
        tmp_path,
        "alpha atomic banking",
        encoder,
        metadata,
        route_operator=candidate_operator,
    )
    reused = reconstruct_blueprint(
        store,
        tmp_path,
        "alpha atomic banking",
        encoder,
        metadata,
        route_operator=candidate_operator,
    )

    assert candidate.cache_hit is False
    assert candidate.materialization_id != incumbent.materialization_id
    assert reused.cache_hit is True
    assert reused.materialization_id == candidate.materialization_id


def test_proved_binding_refuses_builder_as_its_own_judge() -> None:
    with pytest.raises(StateTransitionRefused, match="builder"):
        ImplementationBinding(
            "spectral margin",
            "impl/spectral.py",
            "python-module",
            "planted-proved",
            ("test:proof",),
            "same-seat",
            "same-seat",
        )


def test_heading_anchor_beats_a_body_citation_of_the_same_clause() -> None:
    from atlas.blueprint import _resolve_clause

    heading = PourLeaf(
        "design:law::S1-D2::0",
        "clause:heading",
        "sha256:" + "1" * 64,
        "## S1-D2 — spectral conjugate at pour, not at close\n\nThe governing clause.",
        (1.0, 0.0),
        ("sha256:" + "a" * 64,),
        {"trail": ["Atlas", "S1-D2 — spectral conjugate at pour, not at close"]},
    )
    citation = PourLeaf(
        "design:law::Crutches::0",
        "clause:citation",
        "sha256:" + "2" * 64,
        "See S1-D2 — spectral conjugate at pour for the retirement trigger.",
        (0.0, 1.0),
        ("sha256:" + "b" * 64,),
        {"trail": ["Atlas", "Crutches"]},
    )

    assert _resolve_clause(
        (heading, citation), "S1-D2 — spectral conjugate at pour"
    ) == heading


def test_governing_and_ground_jurisdictions_get_distinct_spectral_fibres(
    tmp_path: Path,
) -> None:
    texts = {
        "design/current_a.md": "# Current A\n\ncurrent law requires persisted frames.\n",
        "design/current_b.md": "# Current B\n\ncurrent law requires exact source custody.\n",
        "design/ground_a.md": "# Historical A\n\nhistorical note says frames are not implemented.\n",
        "design/ground_b.md": "# Historical B\n\nhistorical derivation supplies mathematical ground.\n",
    }
    for path, text in texts.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (tmp_path / "impl").mkdir()
    (tmp_path / "impl/frames.py").write_text("def persist(): pass\n", encoding="utf-8")
    documents = (
        DesignDocument("design/current_a.md", "governing"),
        DesignDocument("design/current_b.md", "governing"),
        DesignDocument("design/ground_a.md", "mathematical-ground"),
        DesignDocument("design/ground_b.md", "mathematical-ground"),
    )
    encoder, contract, metadata, _bindings = fixtures(tmp_path)
    bindings = (
        ImplementationBinding(
            "persisted frames",
            "impl/frames.py",
            "python-module",
            "conjecture",
            ("test:frames",),
            "codex-seat",
            None,
        ),
    )
    store = ConceptricStore(tmp_path / "store")
    generation = pour_blueprint(
        store,
        tmp_path,
        documents,
        bindings,
        encoder,
        contract,
        metadata,
        entry_role="governing",
    )

    role_by_logical = {
        clause["logical_id"]: clause["design_role"] for clause in generation.clauses
    }
    for cluster in generation.clusters:
        assert {
            role_by_logical[logical_id]
            for logical_id in cluster["member_logical_ids"]
        } == {cluster["design_role"]}
    result = reconstruct_blueprint(
        ConceptricStore(store.root),
        tmp_path,
        "what does current law require about implemented frames?",
        encoder,
        metadata,
        top_k=2,
        beam=1,
    )
    assert result.results
    assert {item["design_role"] for item in result.results} == {"governing"}
    assert any(item["implements"] for item in result.results)

    ground = reconstruct_blueprint(
        ConceptricStore(store.root),
        tmp_path,
        "what mathematical ground says frames were not implemented?",
        encoder,
        metadata,
        top_k=2,
        beam=1,
        role="mathematical-ground",
    )
    assert ground.results
    assert {item["design_role"] for item in ground.results} == {"mathematical-ground"}
    assert {item["fibre"] for item in ground.results} == {
        generation.role_fibres["mathematical-ground"]
    }
    assert ConceptricStore(store.root).replay().active_fibre == \
        generation.role_fibres["mathematical-ground"]

    returned = reconstruct_blueprint(
        ConceptricStore(store.root),
        tmp_path,
        "what does current law require?",
        encoder,
        metadata,
        top_k=2,
        beam=1,
    )
    assert {item["design_role"] for item in returned.results} == {"governing"}
    assert ConceptricStore(store.root).replay().active_fibre == \
        generation.role_fibres["governing"]


def test_clause_object_identity_changes_when_identical_source_moves_jurisdiction(
    tmp_path: Path,
) -> None:
    path = tmp_path / "design/law.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Law\n\nidentical source bytes.\n", encoding="utf-8")
    encoder, contract, metadata, _bindings = fixtures(tmp_path)

    first = pour_blueprint(
        ConceptricStore(tmp_path / "first"),
        tmp_path,
        (DesignDocument("design/law.md", "governing"),),
        (),
        encoder,
        contract,
        metadata,
    )
    second = pour_blueprint(
        ConceptricStore(tmp_path / "second"),
        tmp_path,
        (DesignDocument("design/law.md", "historical-ground"),),
        (),
        encoder,
        contract,
        metadata,
    )

    assert first.clauses[0]["content_handle"] == second.clauses[0]["content_handle"]
    assert first.clauses[0]["subject_handle"] == second.clauses[0]["subject_handle"]
    assert first.clauses[0]["subject_id"] != second.clauses[0]["subject_id"]
    assert first.clauses[0]["object_id"] != second.clauses[0]["object_id"]


def test_document_move_preserves_explicit_subject_and_content_identity(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "design/original.md"
    second_path = tmp_path / "moved/renamed.md"
    first_path.parent.mkdir(parents=True)
    second_path.parent.mkdir(parents=True)
    text = "# Stable section\n\ncontent whose source path moves.\n"
    first_path.write_text(text, encoding="utf-8")
    second_path.write_text(text, encoding="utf-8")
    encoder, contract, metadata, _bindings = fixtures(tmp_path)

    first = pour_blueprint(
        ConceptricStore(tmp_path / "first-move"),
        tmp_path,
        (DesignDocument("design/original.md", "governing", "stable-document"),),
        (),
        encoder,
        contract,
        metadata,
    )
    second = pour_blueprint(
        ConceptricStore(tmp_path / "second-move"),
        tmp_path,
        (DesignDocument("moved/renamed.md", "governing", "stable-document"),),
        (),
        encoder,
        contract,
        metadata,
    )

    for field in (
        "logical_id",
        "subject_handle",
        "subject_id",
        "content_handle",
        "object_id",
        "exact_byte_hash",
    ):
        assert first.clauses[0][field] == second.clauses[0][field]


def test_fresh_process_reuses_and_warns_on_a_moved_blueprint(tmp_path: Path) -> None:
    documents = write_fixture(tmp_path)
    encoder, contract, metadata, bindings = fixtures(tmp_path)
    store_root = tmp_path / "cold-process-store"
    store = ConceptricStore(store_root)
    generation = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata
    )
    command = [
        sys.executable,
        "-m",
        "atlas.tools.blueprint_fixture_probe",
        "--repo-root",
        str(tmp_path),
        "--store",
        str(store_root),
        "--goal",
        "alpha canonical atomic banking",
        "--top-k",
        "2",
        "--beam",
        "1",
    ]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")

    first = subprocess.run(
        command, text=True, capture_output=True, check=True, env=environment, timeout=20
    )
    second = subprocess.run(
        command, text=True, capture_output=True, check=True, env=environment, timeout=20
    )
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert first_payload["generation_id"] == generation.generation_id
    assert first_payload["cache_hit"] is False
    assert second_payload["cache_hit"] is True
    assert second_payload["materialization_id"] == first_payload["materialization_id"]
    stable_subject = first_payload["results"][0]["subject_handle"]
    old_content = first_payload["results"][0]["content_handle"]

    (tmp_path / "design/atomic.md").write_text(
        "# Alpha atomic banking\n\nalpha one canonical atomic banking path changed.\n",
        encoding="utf-8",
    )
    moved = subprocess.run(
        command, text=True, capture_output=True, check=True, env=environment, timeout=20
    )
    moved_payload = json.loads(moved.stdout)
    assert moved_payload["source_currency"]["source_roots"] == "MOVED"
    assert moved_payload["results"] == second_payload["results"]
    assert moved_payload["cache_hit"] is True

    replacement = pour_blueprint(
        store, tmp_path, documents, bindings, encoder, contract, metadata,
        parent_generation=generation.generation_id,
    )
    repaired = subprocess.run(
        command, text=True, capture_output=True, check=True, env=environment, timeout=20
    )
    repaired_payload = json.loads(repaired.stdout)
    assert repaired_payload["generation_id"] == replacement.generation_id
    assert repaired_payload["results"][0]["subject_handle"] == stable_subject
    assert repaired_payload["results"][0]["content_handle"] != old_content


def test_read_warning_refreshes_without_changing_banked_results_or_write_guard(tmp_path):
    from atlas.blueprint import _fresh

    documents = write_fixture(tmp_path)
    encoder, contract, metadata, bindings = fixtures(tmp_path)
    store = ConceptricStore(tmp_path / 'store')
    generation = pour_blueprint(store, tmp_path, documents, bindings, encoder, contract, metadata)
    before = reconstruct_blueprint(store, tmp_path, 'alpha atomic banking', encoder, metadata)
    assert before.source_currency == {'source_roots': 'CURRENT', 'moved': []}
    source = tmp_path / 'design/atomic.md'
    original = source.read_bytes()
    source.unlink()
    missing = reconstruct_blueprint(store, tmp_path, 'alpha atomic banking', encoder, metadata)
    assert missing.cache_hit
    assert missing.results == before.results
    assert missing.source_currency == {
        'source_roots': 'MOVED',
        'moved': [{'path': 'container://design/atomic.md',
                   'expected': hash_bytes(original), 'actual': None}],
    }
    with pytest.raises(StateTransitionRefused, match='before write'):
        _fresh(tmp_path, generation)
    source.write_bytes(original)
    restored = reconstruct_blueprint(store, tmp_path, 'alpha atomic banking', encoder, metadata)
    assert restored.cache_hit
    assert restored.results == before.results
    assert restored.source_currency == before.source_currency


def test_portable_source_keys_and_legacy_generation_reader(tmp_path):
    from atlas.blueprint import BlueprintGeneration, _portable_source_roots, blueprint_source_currency

    documents = write_fixture(tmp_path)
    encoder, contract, metadata, bindings = fixtures(tmp_path)
    store = ConceptricStore(tmp_path / 'store')
    generation = pour_blueprint(store, tmp_path, documents, bindings, encoder, contract, metadata)
    legacy_roots = {key.removeprefix('container://'): digest
                    for key, digest in generation.source_roots.items()}
    fields = generation.hashed_dict()
    fields['source_roots'] = legacy_roots
    legacy = BlueprintGeneration.create(**fields)
    raw = legacy.to_dict()
    assert BlueprintGeneration.from_dict(raw).to_dict() == raw
    assert blueprint_source_currency(tmp_path, legacy)['source_roots'] == 'CURRENT'

    # The same container and declared dataset copied to unrelated absolute roots
    # must mint identical keys. An external source with no dataset declaration refuses.
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    roots = {'atlas/DESIGN_S1.md': 'design-digest', 'paper/manuscript/a.tex': 'paper-digest'}
    expected = {'container://DESIGN_S1.md': 'design-digest',
                'dataset:qrc://manuscript/a.tex': 'paper-digest'}
    for base in (first, second):
        assert _portable_source_roots(roots, base, base / 'atlas', {'qrc': base / 'paper'}) == expected
    with pytest.raises(StateTransitionRefused, match='declare its dataset root'):
        _portable_source_roots(roots, first, first / 'atlas', {})

    # A legacy engine key resolves within a detached container, not its parent.
    detached = tmp_path / 'detached'
    detached.mkdir()
    (detached / 'DESIGN_S1.md').write_text('banked design')
    fields['source_roots'] = {'atlas/DESIGN_S1.md': hash_bytes(b'banked design'),
                             'paper/manuscript/a.tex': 'old-paper-digest'}
    engine_legacy = BlueprintGeneration.create(**fields)
    currency = blueprint_source_currency(detached, engine_legacy)
    assert currency['moved'] == [{'path': 'paper/manuscript/a.tex',
                                  'expected': 'old-paper-digest', 'actual': None}]
