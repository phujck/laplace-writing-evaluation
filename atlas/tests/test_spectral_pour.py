from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from atlas.encoders.deterministic import SyntheticEncoder
from atlas.errors import StateTransitionRefused
from atlas.history import (
    AtlasEvent,
    EventKind,
    GradeAxisContract,
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
from atlas.runtime import collect_runtime_receipt
from atlas.schema import SemanticAtom
from atlas.spectral_pour import (
    COSINE_AFFINITY_SPECTRAL,
    PourLeaf,
    PourMetadata,
    SpectralMargin,
    SpectralPourContract,
    bank_spectral_pour,
    derive_spectral_placement,
    observed_pour_leaf,
    repair_spectral_pour,
)
from atlas.store import ConceptricStore

ROOT = Path(__file__).resolve().parents[2]
SOURCE = SourceRef(
    "test:spectral-pour",
    "sha256:" + "a" * 64,
    "test://spectral-pour",
)
RUNTIME = collect_runtime_receipt(ROOT, observed_at="2026-08-24T21:30:00Z")
PRODUCER = ProducerRef("test-provider", "deterministic", "spectral-pour-test")
META = PourMetadata(
    "2026-08-24T21:30:00Z",
    SeatRole.EGO,
    SeatRole.EGO,
    "spectral-pour-test",
    (SOURCE,),
    RUNTIME,
    PRODUCER,
)
CONTRACT = SpectralPourContract(
    "the S1 blueprint is poured under the atlas-rebuild assumption",
    "s1-spectral-pour-test",
    GradeAxisContract(
        "axis-contract:s1-spectral-pour-test/1",
        "source-detail",
        ("cluster", "leaf"),
    ),
    "test-semantic-lens/1",
    SyntheticEncoder.spec,
    "test-cosine/1",
    2,
    1,
    0.5,
)


def handle(digit: str) -> str:
    return "sha256:" + digit * 64


def leaves() -> tuple[PourLeaf, ...]:
    return (
        PourLeaf("frame", "leaf:frame:v1", handle("1"),
                 "persist every retained spectral frame at pour", (1.0, 0.0, 0.0),
                 (handle("a"), handle("1"))),
        PourLeaf("margin", "leaf:margin:v1", handle("2"),
                 "measure the discarded energy margin on the real pour", (0.96, 0.04, 0.0),
                 (handle("a"), handle("2"))),
        PourLeaf("replay", "leaf:replay:v1", handle("3"),
                 "cold replay reconstructs the same paired faces", (0.0, 1.0, 0.0),
                 (handle("b"), handle("3"))),
        PourLeaf("repair", "leaf:repair:v1", handle("4"),
                 "a dirty leaf repairs only its ancestor frame", (0.04, 0.96, 0.0),
                 (handle("b"), handle("4"))),
    )


def test_placement_is_vector_derived_and_input_order_invariant() -> None:
    forward = derive_spectral_placement(leaves(), 2)
    reverse = derive_spectral_placement(tuple(reversed(leaves())), 2)

    assert forward == reverse
    assert {cluster.member_logical_ids for cluster in forward} == {
        ("frame", "margin"),
        ("repair", "replay"),
    }


def test_content_hash_order_does_not_define_spectral_neighbourhoods() -> None:
    semantic = (
        PourLeaf("a", "leaf:a", handle("1"), "a", (1.0, 0.0), (handle("a"), handle("1"))),
        PourLeaf("b", "leaf:b", handle("2"), "b", (0.98, 0.20), (handle("a"), handle("2"))),
        PourLeaf("c", "leaf:c", handle("3"), "c", (0.90, 0.40), (handle("a"), handle("3"))),
        PourLeaf("d", "leaf:d", handle("4"), "d", (-0.20, 0.98), (handle("b"), handle("4"))),
        PourLeaf("e", "leaf:e", handle("5"), "e", (-0.50, 0.86), (handle("b"), handle("5"))),
    )
    rehashed = tuple(
        replace(leaf, content_handle=handle(str(6 - index)))
        for index, leaf in enumerate(semantic, start=1)
    )

    assert derive_spectral_placement(semantic, 2) == \
        derive_spectral_placement(rehashed, 2)


def test_real_pour_persists_complete_frames_and_measured_margin_atomically(
    tmp_path: Path,
) -> None:
    store = ConceptricStore(tmp_path / "spectral")
    banked = bank_spectral_pour(store, CONTRACT, leaves(), META)
    state = store.replay()

    assert state.lifecycle == LifecyclePhase.AWAKE
    assert (state.active_assumption, state.active_fibre) == (
        CONTRACT.assumption,
        CONTRACT.fibre,
    )
    assert len(banked.promotions) == 2
    assert banked.receipt.placement_operator == COSINE_AFFINITY_SPECTRAL
    assert len(banked.receipt.margins) == 2
    assert banked.observation_event_id in state.observation_events
    assert state.observation_events[banked.observation_event_id].payload == banked.receipt.to_dict()
    for cluster_id, promotion in banked.promotions.items():
        spectral = state.graph_objects[promotion.spectral_object_id]
        frame = spectral.attributes["frame"]
        margin = next(item for item in banked.receipt.margins if item.cluster_id == cluster_id)
        assert frame["basis"]
        assert len(frame["coordinates"]) == len(promotion.members)
        assert frame["truncation_residual"] == margin.truncation_residual
        assert margin.signed_margin == pytest.approx(
            margin.phi - margin.truncation_residual
        )
        assert state.graph_objects[promotion.coarse_object_id].attributes[
            "goal_closure_claim"
        ]["status"] == "unmeasured"


def test_same_up_transform_survives_contextual_leaf_address_migration(
    tmp_path: Path,
) -> None:
    store = ConceptricStore(tmp_path / "address-migration")
    first = bank_spectral_pour(store, CONTRACT, leaves(), META)
    migrated = tuple(
        replace(leaf, object_id=leaf.object_id + ":schema-v2") for leaf in leaves()
    )

    second = bank_spectral_pour(store, CONTRACT, migrated, META)

    assert second.receipt.pour_handle != first.receipt.pour_handle
    assert {
        receipt.act_handle for receipt in second.promotions.values()
    } == {
        receipt.act_handle for receipt in first.promotions.values()
    }
    assert set(second.receipt.leaf_object_ids) == {
        leaf.object_id for leaf in migrated
    }


def test_cold_process_replay_reconstructs_the_same_spectral_receipts(tmp_path: Path) -> None:
    root = tmp_path / "cold-replay"
    store = ConceptricStore(root)
    banked = bank_spectral_pour(store, CONTRACT, leaves(), META)
    warm = store.replay()

    reopened = ConceptricStore(root)
    cold = reopened.replay()

    assert cold == warm
    assert cold.observation_events[banked.observation_event_id].payload[
        "pour_handle"
    ] == banked.receipt.pour_handle
    assert {
        item.attributes["node_handle"]
        for item in cold.graph_objects.values()
        if item.kind == "spectral-representation"
    } == {receipt.node_handle for receipt in banked.promotions.values()}


def test_dirty_leaf_repairs_one_ancestor_and_carries_untouched_frame_identity(
    tmp_path: Path,
) -> None:
    store = ConceptricStore(tmp_path / "repair")
    banked = bank_spectral_pour(store, CONTRACT, leaves(), META)
    old = next(leaf for leaf in banked.leaves if leaf.logical_id == "frame")
    replacement = replace(
        old,
        object_id="leaf:frame:v2",
        content_handle=handle("9"),
        text="persist every retained spectral frame at pour, including repair",
        vector=(0.99, 0.01, 0.0),
        source_chain=(handle("a"), handle("9")),
    )
    before = store.replay()
    repaired = repair_spectral_pour(store, banked, replacement, META)
    after = store.replay()

    assert repaired.receipt.mode == "repair"
    assert repaired.receipt.parent_pour_handle == banked.receipt.pour_handle
    assert len(repaired.receipt.touched_cluster_ids) == 1
    affected = repaired.receipt.touched_cluster_ids[0]
    assert repaired.promotions[affected].node_handle != banked.promotions[affected].node_handle
    untouched = {
        cluster.cluster_id
        for cluster in banked.receipt.placement
        if cluster.cluster_id != affected
    }
    assert repaired.receipt.untouched_node_handles == tuple(
        banked.promotions[cluster_id].node_handle for cluster_id in untouched
    )
    for cluster_id in untouched:
        object_id = banked.promotions[cluster_id].spectral_object_id
        assert after.graph_objects[object_id] == before.graph_objects[object_id]
    assert after.observation_events[repaired.observation_event_id].payload == \
        repaired.receipt.to_dict()


def test_append_many_rolls_back_the_complete_packet_on_a_late_refusal(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path / "atomic")

    def lifecycle(receipt_id: str) -> AtlasEvent:
        return AtlasEvent.create(
            occurred_at="2026-08-24T21:30:00Z",
            kind=EventKind.LIFECYCLE,
            producer=SeatRole.EGO,
            actor=SeatRole.EGO,
            subject=f"lifecycle:{receipt_id}",
            assumption=None,
            fibre=None,
            correlation_id="atomic-pour-test",
            causation_ids=(),
            provenance=(SOURCE,),
            residual=Residual(
                ResidualStatus.UNKNOWN,
                None,
                None,
                "not-applicable",
                "control event",
            ),
            runtime=RUNTIME,
            producer_ref=PRODUCER,
            validity=Validity.VALID,
            payload=LifecycleTransition(
                LifecycleAction.COLD_WAKE,
                LifecyclePhase.SLEEPING,
                LifecyclePhase.AWAKE,
                receipt_id,
            ).to_dict(),
        )

    with pytest.raises(StateTransitionRefused):
        store.append_many((lifecycle("first"), lifecycle("second-invalid")))

    assert store.events() == ()
    assert store.replay().lifecycle == LifecyclePhase.SLEEPING


def test_phi_and_chi_are_required_and_margin_round_trip_is_strict() -> None:
    with pytest.raises(TypeError):
        SpectralPourContract(  # type: ignore[call-arg]
            CONTRACT.assumption,
            CONTRACT.fibre,
            CONTRACT.grade_contract,
            CONTRACT.lens_id,
            CONTRACT.encoder_spec,
            CONTRACT.metric_version,
            CONTRACT.cluster_count,
        )
    with pytest.raises(StateTransitionRefused, match="phi"):
        SpectralPourContract(
            CONTRACT.assumption,
            CONTRACT.fibre,
            CONTRACT.grade_contract,
            CONTRACT.lens_id,
            CONTRACT.encoder_spec,
            CONTRACT.metric_version,
            CONTRACT.cluster_count,
            CONTRACT.chi,
            1.1,
        )
    with pytest.raises(StateTransitionRefused, match="phi"):
        SpectralPourContract(
            CONTRACT.assumption,
            CONTRACT.fibre,
            CONTRACT.grade_contract,
            CONTRACT.lens_id,
            CONTRACT.encoder_spec,
            CONTRACT.metric_version,
            CONTRACT.cluster_count,
            CONTRACT.chi,
            0.0,
        )

    margin = SpectralMargin(
        "cluster:test",
        handle("c"),
        handle("d"),
        0.2,
        0.5,
        0.3,
        False,
        True,
        False,
    )
    assert SpectralMargin.from_dict(margin.to_dict()) == margin


def test_lens_and_encoder_spec_bound_the_raw_vector_comparability_domain() -> None:
    other_lens = replace(CONTRACT, lens_id="different-semantic-lens/1")
    other_model = replace(
        CONTRACT,
        encoder_spec=replace(
            CONTRACT.encoder_spec,
            model_artifact_digest="sha256:" + "8" * 64,
        ),
    )

    assert other_lens.vector_space_id != CONTRACT.vector_space_id
    assert other_model.vector_space_id != CONTRACT.vector_space_id
    assert "provider" not in CONTRACT.encoder_spec.to_dict()
    assert "device" not in CONTRACT.encoder_spec.to_dict()


def test_observed_leaf_binds_exact_atom_content_and_complete_source_chain() -> None:
    text = "exact observed row\n"
    from atlas.ids import hash_bytes
    atom = SemanticAtom.create(
        snapshot_id=handle("1"), generation_id=handle("2"), node_id="rows.jsonl",
        path="rows.jsonl", span_id=handle("3"), start=4, end=4 + len(text),
        source_content_hash=handle("4"), content_handle=hash_bytes(text.encode()),
        content_utf8=text, kind="jsonl_row", trail=(), meta={"row_start": 1, "row_end": 1},
        governance_ref={"record": "finding", "id": "F-1"},
    )
    leaf = observed_pour_leaf(
        atom, logical_id="F-1", object_id="leaf:F-1", vector=(1.0, 0.0)
    )
    assert leaf.text == text and leaf.content_handle == atom.content_handle
    assert leaf.source_chain == (
        atom.snapshot_id, atom.generation_id, atom.node_id, atom.span_id,
        atom.atom_id, atom.content_handle,
    )
    assert leaf.attributes["atom_id"] == atom.atom_id

    forged = replace(atom, content_utf8=text + "x")
    with pytest.raises(StateTransitionRefused):
        observed_pour_leaf(
            forged, logical_id="F-1", object_id="leaf:F-1", vector=(1.0, 0.0)
        )


def test_dense_observed_placement_refuses_above_2048_without_sampling() -> None:
    too_many = tuple(
        PourLeaf(
            f"leaf-{index}", f"object-{index}", handle(str(index % 9 + 1)),
            f"text-{index}", (float(index), 1.0), (handle("a"), handle(str(index % 9 + 1))),
        )
        for index in range(2049)
    )
    with pytest.raises(StateTransitionRefused, match="declared cap"):
        derive_spectral_placement(too_many, 2)
