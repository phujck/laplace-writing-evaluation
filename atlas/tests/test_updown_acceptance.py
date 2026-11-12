from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from atlas.history import (
    GradeAxisContract,
    ProducerRef,
    ResidualStatus,
    SeatRole,
    SourceRef,
    TransportReceipt,
)
from atlas.runtime import collect_runtime_receipt
from atlas.store import ConceptricStore
from atlas.updown import ChildLeaf, UpInputs, down, up
from atlas.updown_acceptance import (
    AcceptanceMetadata,
    PlantedLeaf,
    PlantedProbe,
    PlantedWorld,
    bank_planted_world,
    bank_two_assumption_worlds,
    derive_placement,
    repair_dirty_leaf,
)
from atlas.updown_history import GoalClosureStatus

ROOT = Path(__file__).resolve().parents[2]
SOURCE = SourceRef(
    "test:planted-updown-world",
    "sha256:" + "a" * 64,
    "test://planted-updown-world",
)
META = AcceptanceMetadata(
    "2026-08-24T18:30:00Z",
    SeatRole.EGO,
    SeatRole.EGO,
    "planted-updown-acceptance",
    (SOURCE,),
    collect_runtime_receipt(ROOT, observed_at="2026-08-24T18:30:00Z"),
    ProducerRef("test-provider", "deterministic", "system-test"),
)


def handle(digit: str) -> str:
    return "sha256:" + digit * 64


def world() -> PlantedWorld:
    leaves = (
        PlantedLeaf(
            "up-frame",
            "leaf:up-frame:v1",
            handle("1"),
            "UP retains the spectral frame and exact member handles",
            (1.0, 0.0, 0.0),
            (handle("a"), handle("b"), handle("1")),
        ),
        PlantedLeaf(
            "down-cycle",
            "leaf:down-cycle:v1",
            handle("2"),
            "DOWN prolongs from centroid basis and member coordinates",
            (0.95, 0.05, 0.0),
            (handle("a"), handle("c"), handle("2")),
        ),
        PlantedLeaf(
            "closure-law",
            "leaf:closure-law:v1",
            handle("3"),
            "goal closure is measured on planted questions and complete source chains",
            (0.9, 0.1, 0.05),
            (handle("a"), handle("d"), handle("3")),
        ),
        PlantedLeaf(
            "seat-delivery",
            "leaf:seat-delivery:v1",
            handle("4"),
            "seat delivery requires pull reconstruction and accepted acknowledgement",
            (0.0, 1.0, 0.0),
            (handle("e"), handle("f"), handle("4")),
        ),
        PlantedLeaf(
            "fabric-cursor",
            "leaf:fabric-cursor:v1",
            handle("5"),
            "the durable fabric cursor advances only through a banked pull",
            (0.05, 0.95, 0.0),
            (handle("e"), handle("7"), handle("5")),
        ),
        PlantedLeaf(
            "watcher-wake",
            "leaf:watcher-wake:v1",
            handle("6"),
            "the singleton inbox watcher is bound by wake to the durable task",
            (0.1, 0.9, 0.05),
            (handle("e"), handle("8"), handle("6")),
        ),
    )
    by_id = {leaf.logical_id: leaf for leaf in leaves}
    # The queries are planted paraphrase projections, never the target leaves' own vectors.
    # Each family also contains distractors sharing the first source-chain handle.
    query_vectors = {
        "up-frame": (1.0, -0.04, 0.02),
        "down-cycle": (0.96, 0.055, -0.025),
        "closure-law": (0.87, 0.13, 0.09),
        "seat-delivery": (-0.03, 1.0, 0.02),
        "fabric-cursor": (0.045, 0.97, -0.03),
        "watcher-wake": (0.13, 0.88, 0.08),
    }
    probes = tuple(
        PlantedProbe(
            f"probe:{logical_id}",
            f"find {logical_id}",
            query_vectors[logical_id],
            logical_id,
            by_id[logical_id].source_chain,
        )
        for logical_id in (
            "up-frame",
            "down-cycle",
            "closure-law",
            "seat-delivery",
            "fabric-cursor",
            "watcher-wake",
        )
    )
    return PlantedWorld(
        "the clean Atlas must reconstruct the planted law",
        "planted-two-family-world",
        GradeAxisContract(
            "axis-contract:planted-source-detail/1",
            "source-detail",
            ("cluster", "leaf"),
        ),
        "planted-euclidean-cosine/1",
        2,
        2,
        0.05,
        0.0,
        leaves,
        probes,
    )


def second_world() -> PlantedWorld:
    first = world()
    rotated = (
        first.leaves[0],
        first.leaves[3],
        first.leaves[1],
        first.leaves[4],
        first.leaves[2],
        first.leaves[5],
    )
    vectors = tuple(leaf.vector for leaf in rotated)
    leaves = tuple(
        replace(
            leaf,
            logical_id=f"archive-{leaf.logical_id}",
            object_id=f"{leaf.object_id}:archive",
            content_handle=handle(digit),
            text=f"archive-policy view: {leaf.text}",
            vector=vectors[index],
            source_chain=(handle("d"), handle("e"), handle(digit)),
        )
        for index, (leaf, digit) in enumerate(
            zip(first.leaves, ("7", "8", "9", "b", "c", "d"), strict=True)
        )
    )
    probes = tuple(
        PlantedProbe(
            f"probe:{leaf.logical_id}",
            f"find {leaf.logical_id} under the archive policy",
            leaf.vector,
            leaf.logical_id,
            leaf.source_chain,
        )
        for leaf in leaves
    )
    return replace(
        first,
        assumption="the same record is read under the archive-policy assumption",
        fibre="planted-archive-policy-world",
        leaves=leaves,
        probes=probes,
    )


def test_placement_is_derived_and_order_invariant() -> None:
    planted = world()
    forward = derive_placement(planted.leaves, planted.cluster_count)
    reverse = derive_placement(tuple(reversed(planted.leaves)), planted.cluster_count)

    assert forward == reverse
    assert {cluster.member_logical_ids for cluster in forward} == {
        ("closure-law", "down-cycle", "up-frame"),
        ("fabric-cursor", "seat-delivery", "watcher-wake"),
    }
    assert all(
        probe.query_vector != by_id.vector
        for probe in planted.probes
        for by_id in planted.leaves
        if by_id.logical_id == probe.expected_leaf_id
    )
    assert all(
        any(
            leaf.logical_id != probe.expected_leaf_id
            and leaf.source_chain[0] == probe.expected_source_chain[0]
            for leaf in planted.leaves
        )
        for probe in planted.probes
    )


def test_planted_world_banks_measured_two_face_promotions_and_exact_source_chains(
    tmp_path: Path,
) -> None:
    store = ConceptricStore(tmp_path / "planted")
    accepted = bank_planted_world(store, world(), META)
    state = store.replay()

    assert accepted.closure_residual.status == ResidualStatus.WITHIN_BOUND
    assert accepted.closure_residual.value == 0.0
    assert all(answer.passed for answer in accepted.answers)
    assert len(accepted.promotions) == 2
    assert len(state.up_acts) == 2
    for receipt in accepted.promotions.values():
        assert receipt.goal_closure.status == GoalClosureStatus.MEASURED
        assert receipt.goal_closure.probe_set_handle == accepted.probe_set_handle
        assert receipt.goal_closure.probe_event_id == accepted.observation_event_id
        coarse = state.graph_objects[receipt.coarse_object_id]
        assert coarse.attributes["goal_closure_residual"]["value"] == 0.0
        relations = {
            edge.relation
            for edge in state.graph_edges.values()
            if edge.target_object_id == receipt.coarse_object_id
            or edge.source_object_id == receipt.coarse_object_id
        }
        assert {"semantic-face-of", "spectral-face-of", "up-member-of", "down-member-to"} \
            <= relations

    for answer, probe in zip(accepted.answers, accepted.world.probes, strict=True):
        assert answer.leaf_logical_id == probe.expected_leaf_id
        assert answer.source_chain == probe.expected_source_chain

    reopened = ConceptricStore(store.root)
    assert reopened.replay() == state


def test_two_assumptions_force_distinct_strict_joins_and_catch_illicit_crossing(
    tmp_path: Path,
) -> None:
    first = world()
    second = second_world()
    transport = TransportReceipt(
        "transport:retrieval-policy-to-archive-policy",
        first.assumption,
        second.assumption,
        first.fibre,
        second.fibre,
        "declared-assumption-change/1",
        "the archive view changes routing geometry and does not carry old UP faces",
    )
    store = ConceptricStore(tmp_path / "two-assumption")
    accepted = bank_two_assumption_worlds(store, first, second, transport, META)
    state = store.replay()

    assert accepted.first.closure_residual.status == ResidualStatus.WITHIN_BOUND
    assert accepted.second.closure_residual.status == ResidualStatus.WITHIN_BOUND
    assert set(accepted.first_join_ids).isdisjoint(accepted.second_join_ids)
    assert all(state.joins[join_id].strict for join_id in (
        *accepted.first_join_ids,
        *accepted.second_join_ids,
    ))
    assert (state.active_assumption, state.active_fibre) == (
        second.assumption,
        second.fibre,
    )
    assert accepted.illicit_join_refusal_event_id in state.observation_events
    refusal = state.observation_events[accepted.illicit_join_refusal_event_id]
    assert "contradicts its exact UP act" in refusal.payload["refusal"]
    assert len(state.joins) == len(accepted.first_join_ids) + len(accepted.second_join_ids)
    assert ConceptricStore(store.root).replay() == state


def test_down_cycle_is_verified_from_every_planted_cluster() -> None:
    planted = world()
    placement = derive_placement(planted.leaves, planted.cluster_count)
    leaves = {leaf.logical_id: leaf for leaf in planted.leaves}
    for cluster in placement:
        members = tuple(
            leaves[logical_id].child() for logical_id in cluster.member_logical_ids
        )
        result = up(UpInputs(
            planted.assumption,
            planted.fibre,
            planted.grade_contract.axis,
            "leaf",
            "cluster",
            planted.metric_version,
            planted.grade_contract.contract_id,
            planted.chi,
            planted.phi,
            planted.grade_contract.coarse_to_fine,
            members,
        ))
        cycle = down(result.node, children={child.handle: child for child in members})
        assert cycle.verified is True
        assert cycle.round_trip_residual is not None
        assert cycle.round_trip_residual < 1e-8


def test_down_cycle_prices_a_genuinely_lossy_retained_frame() -> None:
    planted = world()
    members = (
        ChildLeaf(handle("a"), "lossy north", (1.0, 0.0, 0.0)),
        ChildLeaf(handle("b"), "lossy east", (0.0, 1.0, 0.0)),
        ChildLeaf(handle("c"), "lossy height", (0.0, 0.0, 1.0)),
        ChildLeaf(handle("d"), "lossy origin", (0.0, 0.0, 0.0)),
    )
    promoted = up(UpInputs(
        planted.assumption,
        planted.fibre,
        planted.grade_contract.axis,
        "leaf",
        "cluster",
        planted.metric_version,
        planted.grade_contract.contract_id,
        1,
        1.0,
        planted.grade_contract.coarse_to_fine,
        members,
    ))
    assert promoted.node is not None
    assert promoted.node.frame is not None
    assert promoted.node.frame.chi_kept == 1
    assert promoted.residual_value > 0.0

    cycle = down(promoted.node, children={child.handle: child for child in members})
    assert cycle.verified is True
    assert cycle.round_trip_residual is not None
    assert cycle.round_trip_residual > 0.0


def test_dirty_leaf_recomputes_one_ancestor_and_preserves_untouched_subtree(
    tmp_path: Path,
) -> None:
    store = ConceptricStore(tmp_path / "incremental")
    accepted = bank_planted_world(store, world(), META)
    original = next(leaf for leaf in accepted.world.leaves if leaf.logical_id == "up-frame")
    replacement = replace(
        original,
        object_id="leaf:up-frame:v2",
        content_handle=handle("9"),
        text="UP v2 retains both faces, its frame, and exact member handles",
        vector=(1.02, 0.0, 0.0),
        source_chain=(handle("a"), handle("b"), handle("9")),
    )
    before_count = store.replay().event_count

    repaired = repair_dirty_leaf(store, accepted, replacement, META)
    after = store.replay()

    assert after.event_count == before_count + 3  # leaf + observation + one UP; exam is fixed
    assert repaired.previous_node_handle != repaired.repaired_node_handle
    assert len(repaired.untouched_cluster_ids) == 1
    assert repaired.untouched_objects_before == repaired.untouched_objects_after
    # Ground truth stays fixed. The replacement therefore exposes the now-stale expected
    # source chain instead of rewriting its own exam and awarding itself a perfect score.
    assert repaired.accepted.closure_residual.status == ResidualStatus.EXCEEDS_BOUND
    assert repaired.accepted.closure_residual.value == 1 / len(accepted.world.probes)
    repaired_answer = next(
        answer
        for answer in repaired.accepted.answers
        if answer.probe_id == "probe:up-frame"
    )
    assert repaired_answer.correct_leaf is True
    assert repaired_answer.complete_source_chain is False
    assert len(after.up_acts) == 3
    assert "leaf:up-frame:v1" in after.graph_objects
    assert "leaf:up-frame:v2" in after.graph_objects
    repaired_event = next(
        event
        for event in store.events()
        if event.event_id
        == repaired.accepted.promotion_event_ids[repaired.affected_cluster_id]
    )
    assert repaired_event.causation_ids == (
        repaired.accepted.observation_event_id,
        accepted.promotion_event_ids[repaired.affected_cluster_id],
    )


def test_incomplete_source_chain_is_a_measured_closure_failure(tmp_path: Path) -> None:
    planted = world()
    first = planted.probes[0]
    bad_probe = replace(first, expected_source_chain=(*first.expected_source_chain, handle("f")))
    bad_world = replace(planted, probes=(bad_probe, *planted.probes[1:]))
    accepted = bank_planted_world(
        ConceptricStore(tmp_path / "closure-failure"),
        bad_world,
        META,
    )

    assert accepted.closure_residual.status == ResidualStatus.EXCEEDS_BOUND
    assert accepted.closure_residual.value == 1 / len(bad_world.probes)
    assert accepted.answers[0].correct_leaf is True
    assert accepted.answers[0].complete_source_chain is False
