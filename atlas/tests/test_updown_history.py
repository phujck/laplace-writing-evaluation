from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from atlas.errors import StateTransitionRefused
from atlas.history import (
    AssumptionSelection,
    AtlasEvent,
    ConceptricObject,
    EventKind,
    GradeAxisContract,
    JoinReceipt,
    LifecycleAction,
    LifecyclePhase,
    LifecycleTransition,
    ProducerRef,
    Residual,
    ResidualStatus,
    SeatRole,
    SourceRef,
    Validity,
    derived_join_id,
)
from atlas.ids import chash
from atlas.runtime import collect_runtime_receipt
from atlas.store import ConceptricStore
from atlas.updown import ChildLeaf, UpInputs, down, up
from atlas.updown_history import (
    EXACT_MEMBER_COVERAGE,
    GOAL_CLOSURE_PROBE_SET_KIND,
    DownActReceipt,
    GoalClosureAnswer,
    GoalClosureClaim,
    GoalClosureObservation,
    GoalClosureProbe,
    GoalClosureProbeSet,
    GoalClosureRoutingCandidate,
    GoalClosureStatus,
    UpActReceipt,
    bind_down_result,
    bind_up_result,
    derived_cluster_id,
    prolongation_event,
    promotion_event,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = SourceRef("test:updown-history", "sha256:" + "9" * 64, "test://updown")
PRODUCER = ProducerRef("test-provider", "deterministic", "system-test")
RUNTIME = collect_runtime_receipt(ROOT, observed_at="2026-08-24T18:00:00Z")
ASSUMPTION = "atlas-history-test"
FIBRE = "two-face-updown"
CONTRACT = GradeAxisContract(
    "axis-contract:test-source-detail/1",
    "source-detail",
    ("coarse", "fine"),
)
CONTROL_RESIDUAL = Residual(
    ResidualStatus.WITHIN_BOUND, 0.0, 0.0, "control", "test control event"
)
UNKNOWN_CLOSURE = Residual(
    ResidualStatus.UNKNOWN,
    None,
    None,
    "goal-closure",
    "pure kernel has not run planted retrieval/source-chain probes",
)
UNKNOWN_ROUND_TRIP = Residual(
    ResidualStatus.UNKNOWN,
    None,
    None,
    "round-trip-relative-error",
    "DOWN reconstructed from retained state without originals",
)


def event(
    kind: EventKind,
    payload: dict,
    *,
    assumption: str | None = None,
    fibre: str | None = None,
) -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at="2026-08-24T18:00:00Z",
        kind=kind,
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        subject=kind.value,
        assumption=assumption,
        fibre=fibre,
        correlation_id="updown-history-test",
        causation_ids=(),
        provenance=(SOURCE,),
        residual=CONTROL_RESIDUAL,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=payload,
    )


def setup_store(root: Path) -> tuple[ConceptricStore, UpInputs, dict[str, str]]:
    store = ConceptricStore(root)
    store.append(
        event(
            EventKind.LIFECYCLE,
            LifecycleTransition(
                LifecycleAction.COLD_WAKE,
                LifecyclePhase.SLEEPING,
                LifecyclePhase.AWAKE,
                "updown-history-cold-wake",
            ).to_dict(),
        )
    )
    store.append(
        event(
            EventKind.ASSUMPTION,
            AssumptionSelection(ASSUMPTION, FIBRE, 1.0, ()).to_dict(),
            assumption=ASSUMPTION,
            fibre=FIBRE,
        )
    )
    store.append(event(EventKind.GRADE_AXIS, CONTRACT.to_dict()))
    children = (
        ChildLeaf("sha256:" + "1" * 64, "alpha source chain", (1.0, 0.0)),
        ChildLeaf("sha256:" + "2" * 64, "beta source chain", (0.0, 1.0)),
        ChildLeaf("sha256:" + "3" * 64, "gamma source chain", (0.8, 0.2)),
    )
    object_ids = {child.handle: f"leaf:{index}" for index, child in enumerate(children)}
    for child in children:
        item = ConceptricObject(
            object_ids[child.handle],
            "source-leaf",
            child.handle,
            ASSUMPTION,
            FIBRE,
            CONTRACT.contract_id,
            "fine",
            (SOURCE,),
            {
                "logical_id": object_ids[child.handle],
                "text": child.text,
                "vector": list(child.vector),
                "source_chain": [SOURCE.digest, child.handle],
            },
        )
        store.append(
            event(
                EventKind.OBJECT,
                item.to_dict(),
                assumption=ASSUMPTION,
                fibre=FIBRE,
            )
        )
    inputs = UpInputs(
        ASSUMPTION,
        FIBRE,
        CONTRACT.axis,
        "fine",
        "coarse",
        "test-metric/1",
        CONTRACT.contract_id,
        1,
        1.0,
        CONTRACT.coarse_to_fine,
        children,
    )
    return store, inputs, object_ids


def promote(
    store: ConceptricStore,
    inputs: UpInputs,
    object_ids: dict[str, str],
) -> tuple[UpActReceipt, AtlasEvent]:
    receipt = bind_up_result(inputs, up(inputs), object_ids)
    promoted = promotion_event(
        receipt,
        occurred_at="2026-08-24T18:01:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE,),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        goal_residual=UNKNOWN_CLOSURE,
    )
    store.append(promoted)
    return receipt, promoted


def test_one_promotion_event_atomically_materializes_both_faces_and_paired_topology(
    tmp_path: Path,
) -> None:
    store, inputs, object_ids = setup_store(tmp_path / "history")
    before = store.replay()
    untouched = {
        object_id: before.graph_objects[object_id].to_dict()
        for object_id in object_ids.values()
    }
    receipt, promoted = promote(store, inputs, object_ids)
    state = store.replay()

    assert state.event_count == before.event_count + 1
    assert state.up_acts[receipt.act_handle] == receipt
    assert state.up_events[promoted.event_id] == receipt.act_handle
    assert state.graph_objects[receipt.coarse_object_id].content_handle == receipt.node_handle
    assert state.graph_objects[receipt.semantic_object_id].kind == "semantic-representation"
    assert state.graph_objects[receipt.spectral_object_id].kind == "spectral-representation"
    relations = [
        edge.relation
        for edge in state.graph_edges.values()
        if edge.generation_handle == promoted.event_id
    ]
    assert relations.count("semantic-face-of") == 1
    assert relations.count("spectral-face-of") == 1
    assert relations.count("up-member-of") == len(inputs.children)
    assert relations.count("down-member-to") == len(inputs.children)
    assert state.graph_objects[receipt.coarse_object_id].attributes[
        "goal_closure_residual"
    ][
        "status"
    ] == "unknown"
    assert state.graph_objects[receipt.coarse_object_id].attributes[
        "goal_closure_claim"
    ]["status"] == "unmeasured"
    assert state.graph_objects[receipt.coarse_object_id].attributes[
        "truncation_residual"
    ] == receipt.frame.truncation_residual
    assert {
        object_id: state.graph_objects[object_id].to_dict()
        for object_id in object_ids.values()
    } == untouched
    assert store.provider_snapshot()["up_acts"][receipt.act_handle] == receipt.to_dict()

    reopened = ConceptricStore(store.root)
    assert reopened.replay() == state
    assert reopened.provider_snapshot() == store.provider_snapshot()


def test_receipts_are_strict_versioned_round_trips(tmp_path: Path) -> None:
    store, inputs, object_ids = setup_store(tmp_path / "strict")
    receipt, promoted = promote(store, inputs, object_ids)
    assert UpActReceipt.from_dict(receipt.to_dict()) == receipt

    down_receipt = bind_down_result(promoted.event_id, receipt, down(up(inputs).node))
    assert DownActReceipt.from_dict(down_receipt.to_dict()) == down_receipt
    malformed = {**receipt.to_dict(), "surprise": True}
    with pytest.raises(Exception, match="fields do not match"):
        UpActReceipt.from_dict(malformed)


def test_promotion_refuses_missing_or_mismatched_member_without_partial_append(
    tmp_path: Path,
) -> None:
    store, inputs, object_ids = setup_store(tmp_path / "refusal")
    result = up(inputs)
    receipt = bind_up_result(inputs, result, object_ids)
    bad_member = replace(receipt.members[0], content_handle="sha256:" + "f" * 64)
    bad = replace(
        receipt,
        members=(bad_member, *receipt.members[1:]),
        semantic_sources=tuple(
            bad_member.content_handle if handle == receipt.members[0].content_handle else handle
            for handle in receipt.semantic_sources
        ),
    )
    promoted = promotion_event(
        bad,
        occurred_at="2026-08-24T18:01:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE,),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        goal_residual=UNKNOWN_CLOSURE,
    )
    count = store.replay().event_count
    with pytest.raises(StateTransitionRefused, match="content handle contradicts"):
        store.append(promoted)
    after = store.replay()
    assert after.event_count == count
    assert receipt.coarse_object_id not in after.graph_objects


def test_promotion_refuses_unknown_or_contradictory_grade_contract(tmp_path: Path) -> None:
    store, inputs, object_ids = setup_store(tmp_path / "contract")
    receipt = bind_up_result(inputs, up(inputs), object_ids)
    wrong_axis = replace(
        receipt.grade_axis,
        contract_id="axis-contract:unknown/1",
    )
    bad = replace(receipt, grade_axis=wrong_axis)
    promoted = promotion_event(
        bad,
        occurred_at="2026-08-24T18:01:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE,),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        goal_residual=UNKNOWN_CLOSURE,
    )
    with pytest.raises(StateTransitionRefused, match="unknown grade-axis contract"):
        store.append(promoted)


def test_pure_promotion_cannot_claim_measured_goal_closure(tmp_path: Path) -> None:
    _store, inputs, object_ids = setup_store(tmp_path / "closure")
    receipt = bind_up_result(inputs, up(inputs), object_ids)
    false_claim = Residual(
        ResidualStatus.WITHIN_BOUND,
        0.0,
        0.1,
        "goal-closure",
        "not actually measured",
    )
    with pytest.raises(StateTransitionRefused, match="cannot claim measured"):
        promotion_event(
            receipt,
            occurred_at="2026-08-24T18:01:00Z",
            producer=SeatRole.EGO,
            actor=SeatRole.EGO,
            correlation_id="updown-history-test",
            provenance=(SOURCE,),
            runtime=RUNTIME,
            producer_ref=PRODUCER,
            goal_residual=false_claim,
        )

    with pytest.raises(StateTransitionRefused, match="typed claim"):
        replace(receipt, goal_closure="MEASURED: closure 0.001, passed")


def test_strict_join_resolves_exact_faces_of_banked_up_act(tmp_path: Path) -> None:
    store, inputs, object_ids = setup_store(tmp_path / "strict-join")
    receipt, promoted = promote(store, inputs, object_ids)
    state = store.replay()
    semantic = state.graph_objects[receipt.semantic_object_id]
    spectral = state.graph_objects[receipt.spectral_object_id]
    join_id = derived_join_id(
        receipt.node_handle,
        ASSUMPTION,
        FIBRE,
        receipt.semantic_object_id,
        receipt.spectral_object_id,
        receipt.act_handle,
    )
    join = JoinReceipt(
        join_id,
        receipt.node_handle,
        ASSUMPTION,
        FIBRE,
        "strict-up-two-face-join/1",
        semantic.content_handle,
        spectral.content_handle,
        (SOURCE,),
        CONTROL_RESIDUAL,
        receipt.semantic_object_id,
        receipt.spectral_object_id,
        receipt.act_handle,
    )
    joined = AtlasEvent.create(
        occurred_at="2026-08-24T18:01:30Z",
        kind=EventKind.JOIN,
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        subject=join.join_id,
        assumption=ASSUMPTION,
        fibre=FIBRE,
        correlation_id="updown-history-test",
        causation_ids=(promoted.event_id,),
        provenance=(SOURCE,),
        residual=CONTROL_RESIDUAL,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=join.to_dict(),
    )
    store.append(joined)

    replayed = store.replay()
    assert replayed.joins[join.join_id] == join
    join_object = replayed.graph_objects[f"join:{join.join_id}"]
    assert join_object.attributes["up_act_handle"] == receipt.act_handle
    assert any(
        edge.relation == "conjugate-joins"
        and edge.source_object_id == receipt.semantic_object_id
        and edge.target_object_id == join_object.object_id
        for edge in replayed.graph_edges.values()
    )

    forged_semantic_id = "semantic:" + ("f" * 64)
    forged_join = JoinReceipt(
        derived_join_id(
            receipt.node_handle,
            ASSUMPTION,
            FIBRE,
            forged_semantic_id,
            receipt.spectral_object_id,
            receipt.act_handle,
        ),
        receipt.node_handle,
        ASSUMPTION,
        FIBRE,
        "strict-up-two-face-join/1",
        semantic.content_handle,
        spectral.content_handle,
        (SOURCE,),
        CONTROL_RESIDUAL,
        forged_semantic_id,
        receipt.spectral_object_id,
        receipt.act_handle,
    )
    forged_event = AtlasEvent.create(
        occurred_at="2026-08-24T18:01:31Z",
        kind=EventKind.JOIN,
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        subject=forged_join.join_id,
        assumption=ASSUMPTION,
        fibre=FIBRE,
        correlation_id="updown-history-test",
        causation_ids=(promoted.event_id,),
        provenance=(SOURCE,),
        residual=CONTROL_RESIDUAL,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=forged_join.to_dict(),
    )
    with pytest.raises(StateTransitionRefused, match="exact faces"):
        store.append(forged_event)


def test_measured_goal_closure_requires_and_resolves_probe_evidence(tmp_path: Path) -> None:
    store, inputs, object_ids = setup_store(tmp_path / "closure-evidence")
    receipt = bind_up_result(inputs, up(inputs), object_ids)
    probes = tuple(
        GoalClosureProbe(
            f"probe:{index}",
            f"find {child.text}",
            child.vector,
            object_ids[child.handle],
            (SOURCE.digest, child.handle),
        )
        for index, child in enumerate(inputs.children)
    )
    probe_set = GoalClosureProbeSet(
        ASSUMPTION,
        FIBRE,
        EXACT_MEMBER_COVERAGE,
        probes,
    )
    probe_handle = probe_set.handle
    probe_source = SourceRef("test:closure-probes", probe_handle, "test://closure-probes")
    probe_item = ConceptricObject(
        f"goal-closure-probe-set:{probe_handle}",
        GOAL_CLOSURE_PROBE_SET_KIND,
        probe_handle,
        ASSUMPTION,
        FIBRE,
        CONTRACT.contract_id,
        "fine",
        (probe_source,),
        probe_set.to_dict(),
    )
    probe_event = AtlasEvent.create(
        occurred_at="2026-08-24T18:00:20Z",
        kind=EventKind.OBJECT,
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        subject=f"goal-closure-probe-set:{probe_handle}",
        assumption=ASSUMPTION,
        fibre=FIBRE,
        correlation_id="updown-history-test",
        causation_ids=(),
        provenance=(probe_source,),
        residual=CONTROL_RESIDUAL,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=probe_item.to_dict(),
    )
    store.append(probe_event)
    measured_residual = Residual(
        ResidualStatus.WITHIN_BOUND,
        0.0,
        0.1,
        "goal-closure",
        "measured on the cited planted probe set",
    )
    routing_candidate = GoalClosureRoutingCandidate(
        derived_cluster_id(
            tuple(object_ids[member.content_handle] for member in receipt.members)
        ),
        receipt.node_handle,
        receipt.centroid,
        receipt.members,
    )
    routed_answers = tuple(
        GoalClosureAnswer(
            probe.probe_id,
            probe.expected_leaf_id,
            probe.expected_source_chain,
            True,
            True,
            True,
        )
        for probe in probes
    )
    observation = AtlasEvent.create(
        occurred_at="2026-08-24T18:00:30Z",
        kind=EventKind.OBSERVATION,
        producer=SeatRole.SENSORIUM,
        actor=SeatRole.SENSORIUM,
        subject="closure-probe-observation",
        assumption=ASSUMPTION,
        fibre=FIBRE,
        correlation_id="updown-history-test",
        causation_ids=(probe_event.event_id,),
        provenance=(probe_source,),
        residual=measured_residual,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=GoalClosureObservation(
            probe_handle,
            (receipt.node_handle,),
            (routing_candidate,),
            routed_answers,
        ).to_dict(),
    )
    store.append(observation)
    measured_claim = GoalClosureClaim(
        GoalClosureStatus.MEASURED,
        probe_handle,
        observation.event_id,
        chash(observation.payload),
        "declared planted probes executed",
    )
    measured_receipt = replace(receipt, goal_closure=measured_claim)

    with pytest.raises(StateTransitionRefused, match="causally cite"):
        promotion_event(
            measured_receipt,
            occurred_at="2026-08-24T18:01:00Z",
            producer=SeatRole.EGO,
            actor=SeatRole.EGO,
            correlation_id="updown-history-test",
            provenance=(SOURCE, probe_source),
            runtime=RUNTIME,
            producer_ref=PRODUCER,
            goal_residual=measured_residual,
        )

    forged_receipt = replace(
        measured_receipt,
        goal_closure=replace(
            measured_receipt.goal_closure,
            observation_handle="sha256:" + "f" * 64,
        ),
    )
    forged = promotion_event(
        forged_receipt,
        occurred_at="2026-08-24T18:01:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE, probe_source),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        goal_residual=measured_residual,
        causation_ids=(observation.event_id,),
    )
    with pytest.raises(StateTransitionRefused, match="exact observation payload"):
        store.append(forged)

    empty_payload = {
        "schema_version": GoalClosureObservation.SCHEMA_VERSION,
        "phase": "preview",
        "probe_set_handle": probe_handle,
        "promoted_handles": [receipt.node_handle],
        "candidates": [routing_candidate.to_dict()],
        "answers": [],
    }
    empty_observation = AtlasEvent.create(
        occurred_at="2026-08-24T18:00:40Z",
        kind=EventKind.OBSERVATION,
        producer=SeatRole.SENSORIUM,
        actor=SeatRole.SENSORIUM,
        subject="closure-probe-empty-exam",
        assumption=ASSUMPTION,
        fibre=FIBRE,
        correlation_id="updown-history-test",
        causation_ids=(probe_event.event_id,),
        provenance=(probe_source,),
        residual=measured_residual,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=empty_payload,
    )
    store.append(empty_observation)
    empty_receipt = replace(
        receipt,
        goal_closure=GoalClosureClaim(
            GoalClosureStatus.MEASURED,
            probe_handle,
            empty_observation.event_id,
            chash(empty_payload),
            "a perfect score on no answers must be refused",
        ),
    )
    empty_promotion = promotion_event(
        empty_receipt,
        occurred_at="2026-08-24T18:01:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE, probe_source),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        goal_residual=measured_residual,
        causation_ids=(empty_observation.event_id,),
    )
    with pytest.raises(StateTransitionRefused, match="empty answer list"):
        store.append(empty_promotion)

    laundered_residual = replace(measured_residual, value=0.1)
    laundering = promotion_event(
        measured_receipt,
        occurred_at="2026-08-24T18:01:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE, probe_source),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        goal_residual=laundered_residual,
        causation_ids=(observation.event_id,),
    )
    with pytest.raises(StateTransitionRefused, match="contradicts its closure observation"):
        store.append(laundering)

    mislabeled_residual = Residual(
        ResidualStatus.EXCEEDS_BOUND,
        0.0,
        0.0,
        "goal-closure",
        "a perfect answer set cannot be labeled exceeds-bound",
    )
    mislabeled_observation = AtlasEvent.create(
        occurred_at="2026-08-24T18:00:50Z",
        kind=EventKind.OBSERVATION,
        producer=SeatRole.SENSORIUM,
        actor=SeatRole.SENSORIUM,
        subject="closure-probe-mislabeled-status",
        assumption=ASSUMPTION,
        fibre=FIBRE,
        correlation_id="updown-history-test",
        causation_ids=(probe_event.event_id,),
        provenance=(probe_source,),
        residual=mislabeled_residual,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=observation.payload,
    )
    store.append(mislabeled_observation)
    mislabeled_receipt = replace(
        measured_receipt,
        goal_closure=replace(
            measured_receipt.goal_closure,
            probe_event_id=mislabeled_observation.event_id,
        ),
    )
    mislabeled_promotion = promotion_event(
        mislabeled_receipt,
        occurred_at="2026-08-24T18:01:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE, probe_source),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        goal_residual=mislabeled_residual,
        causation_ids=(mislabeled_observation.event_id,),
    )
    with pytest.raises(StateTransitionRefused, match="status contradicts"):
        store.append(mislabeled_promotion)

    forged_answers = (
        replace(
            routed_answers[0],
            selected_leaf_id=probes[1].expected_leaf_id,
            source_chain=probes[1].expected_source_chain,
            correct_leaf=False,
            complete_source_chain=False,
            passed=False,
        ),
        *routed_answers[1:],
    )
    forged_route_residual = replace(
        measured_residual,
        status=ResidualStatus.EXCEEDS_BOUND,
        value=1 / len(forged_answers),
    )
    forged_route_payload = GoalClosureObservation(
        probe_handle,
        (receipt.node_handle,),
        (routing_candidate,),
        forged_answers,
    ).to_dict()
    forged_route_observation = AtlasEvent.create(
        occurred_at="2026-08-24T18:00:55Z",
        kind=EventKind.OBSERVATION,
        producer=SeatRole.SENSORIUM,
        actor=SeatRole.SENSORIUM,
        subject="closure-probe-forged-route",
        assumption=ASSUMPTION,
        fibre=FIBRE,
        correlation_id="updown-history-test",
        causation_ids=(probe_event.event_id,),
        provenance=(probe_source,),
        residual=forged_route_residual,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=forged_route_payload,
    )
    store.append(forged_route_observation)
    forged_route_receipt = replace(
        receipt,
        goal_closure=GoalClosureClaim(
            GoalClosureStatus.MEASURED,
            probe_handle,
            forged_route_observation.event_id,
            chash(forged_route_payload),
            "truth-consistent answer fields cannot substitute for derived routing",
        ),
    )
    forged_route_promotion = promotion_event(
        forged_route_receipt,
        occurred_at="2026-08-24T18:01:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE, probe_source),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        goal_residual=forged_route_residual,
        causation_ids=(forged_route_observation.event_id,),
    )
    with pytest.raises(StateTransitionRefused, match="not derived from banked routing"):
        store.append(forged_route_promotion)

    thin_probe_set = GoalClosureProbeSet(
        ASSUMPTION,
        FIBRE,
        EXACT_MEMBER_COVERAGE,
        (probes[0],),
    )
    thin_probe_handle = thin_probe_set.handle
    thin_probe_source = SourceRef(
        "test:thin-closure-probes",
        thin_probe_handle,
        "test://thin-closure-probes",
    )
    thin_probe_item = ConceptricObject(
        f"goal-closure-probe-set:{thin_probe_handle}",
        GOAL_CLOSURE_PROBE_SET_KIND,
        thin_probe_handle,
        ASSUMPTION,
        FIBRE,
        CONTRACT.contract_id,
        "fine",
        (thin_probe_source,),
        thin_probe_set.to_dict(),
    )
    thin_probe_event = AtlasEvent.create(
        occurred_at="2026-08-24T18:00:56Z",
        kind=EventKind.OBJECT,
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        subject=f"goal-closure-probe-set:{thin_probe_handle}",
        assumption=ASSUMPTION,
        fibre=FIBRE,
        correlation_id="updown-history-test",
        causation_ids=(),
        provenance=(thin_probe_source,),
        residual=CONTROL_RESIDUAL,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=thin_probe_item.to_dict(),
    )
    store.append(thin_probe_event)
    thin_payload = GoalClosureObservation(
        thin_probe_handle,
        (receipt.node_handle,),
        (routing_candidate,),
        (routed_answers[0],),
    ).to_dict()
    thin_observation = AtlasEvent.create(
        occurred_at="2026-08-24T18:00:57Z",
        kind=EventKind.OBSERVATION,
        producer=SeatRole.SENSORIUM,
        actor=SeatRole.SENSORIUM,
        subject="closure-probe-self-chosen-exam",
        assumption=ASSUMPTION,
        fibre=FIBRE,
        correlation_id="updown-history-test",
        causation_ids=(thin_probe_event.event_id,),
        provenance=(thin_probe_source,),
        residual=measured_residual,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=thin_payload,
    )
    store.append(thin_observation)
    thin_receipt = replace(
        receipt,
        goal_closure=GoalClosureClaim(
            GoalClosureStatus.MEASURED,
            thin_probe_handle,
            thin_observation.event_id,
            chash(thin_payload),
            "one easy probe cannot buy measured status for three candidate members",
        ),
    )
    thin_promotion = promotion_event(
        thin_receipt,
        occurred_at="2026-08-24T18:01:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE, thin_probe_source),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        goal_residual=measured_residual,
        causation_ids=(thin_observation.event_id,),
    )
    with pytest.raises(StateTransitionRefused, match="exactly one probe"):
        store.append(thin_promotion)

    promoted = promotion_event(
        measured_receipt,
        occurred_at="2026-08-24T18:01:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE, probe_source),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        goal_residual=measured_residual,
        causation_ids=(observation.event_id,),
    )
    store.append(promoted)
    coarse = store.replay().graph_objects[measured_receipt.coarse_object_id]
    assert coarse.attributes["goal_closure_claim"]["probe_set_handle"] == probe_handle
    assert coarse.attributes["goal_closure_residual"]["value"] == 0.0


def test_down_cites_exact_up_and_preserves_unknown_when_unverified(tmp_path: Path) -> None:
    store, inputs, object_ids = setup_store(tmp_path / "down-unverified")
    result = up(inputs)
    receipt, promoted = promote(store, inputs, object_ids)
    down_receipt = bind_down_result(promoted.event_id, receipt, down(result.node))
    prolonged = prolongation_event(
        down_receipt,
        receipt,
        occurred_at="2026-08-24T18:02:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE,),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        residual=UNKNOWN_ROUND_TRIP,
    )
    draft = replace(prolonged, event_id="", causation_ids=())
    false_cause = replace(draft, event_id=draft.computed_id())
    with pytest.raises(StateTransitionRefused, match="exactly its corresponding UP"):
        store.append(false_cause)
    store.append(prolonged)
    state = store.replay()
    assert state.down_acts[down_receipt.act_handle].round_trip_residual is None
    assert prolonged.causation_ids == (promoted.event_id,)


def test_verified_down_banks_measured_round_trip_residual(tmp_path: Path) -> None:
    store, inputs, object_ids = setup_store(tmp_path / "down-verified")
    result = up(inputs)
    receipt, promoted = promote(store, inputs, object_ids)
    originals = {child.handle: child for child in inputs.children}
    down_result = down(result.node, children=originals)
    down_receipt = bind_down_result(promoted.event_id, receipt, down_result)
    measured = Residual(
        ResidualStatus.WITHIN_BOUND,
        down_result.round_trip_residual,
        1.0,
        "round-trip-relative-error",
        "verified against every original child",
    )
    prolonged = prolongation_event(
        down_receipt,
        receipt,
        occurred_at="2026-08-24T18:02:00Z",
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        correlation_id="updown-history-test",
        provenance=(SOURCE,),
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        residual=measured,
    )
    store.append(prolonged)
    assert store.replay().down_acts[down_receipt.act_handle].round_trip_residual == measured.value
