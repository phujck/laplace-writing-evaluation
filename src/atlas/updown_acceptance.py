"""Planted acceptance harness for the canonical UP/DOWN history seam.

This is deliberately smaller than a corpus runner.  It answers the acceptance questions the
real-notes pour cannot answer because its truth is not planted: membership is derived from
vectors, every promotion enters the one store, questions route coarse-to-fine, the complete
expected source chain is checked, and a dirty leaf recomputes only its ancestor cluster.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .errors import StateTransitionRefused
from .history import (
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
    RuntimeReceipt,
    SeatRole,
    SourceRef,
    TransportReceipt,
    Validity,
    derived_join_id,
)
from .ids import chash
from .spectral_pour import SpectralCluster as DerivedCluster
from .spectral_pour import derive_spectral_placement
from .store import ConceptricStore
from .updown import ChildLeaf, CoarseNode, UpInputs, up
from .updown_history import (
    EXACT_MEMBER_COVERAGE,
    GOAL_CLOSURE_PROBE_SET_KIND,
    GoalClosureAnswer,
    GoalClosureClaim,
    GoalClosureObservation,
    GoalClosureProbe,
    GoalClosureProbeSet,
    GoalClosureRoutingCandidate,
    GoalClosureStatus,
    UpActReceipt,
    UpMemberRef,
    bind_up_result,
    promotion_event,
)


def _require(condition: bool, message: str, **fields: object) -> None:
    if not condition:
        raise StateTransitionRefused(message, **fields)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
    return numerator / (left_norm * right_norm)


@dataclass(frozen=True)
class PlantedLeaf:
    logical_id: str
    object_id: str
    content_handle: str
    text: str
    vector: tuple[float, ...]
    source_chain: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("logical_id", "object_id", "content_handle", "text"):
            _require(bool(str(getattr(self, field)).strip()),
                     "planted leaf field must be non-empty", field=field)
        _require(bool(self.vector), "planted leaf vector must be non-empty")
        _require(bool(self.source_chain) and all(self.source_chain),
                 "planted leaf must carry its complete source chain")

    def child(self) -> ChildLeaf:
        return ChildLeaf(self.content_handle, self.text, self.vector)


@dataclass(frozen=True)
class PlantedProbe:
    probe_id: str
    question: str
    query_vector: tuple[float, ...]
    expected_leaf_id: str
    expected_source_chain: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(bool(self.probe_id.strip()) and bool(self.question.strip()),
                 "planted probe id and question must be non-empty")
        _require(bool(self.query_vector), "planted probe query vector must be non-empty")
        _require(bool(self.expected_leaf_id.strip()) and bool(self.expected_source_chain),
                 "planted probe must declare its exact expected leaf and source chain")


@dataclass(frozen=True)
class PlantedWorld:
    assumption: str
    fibre: str
    grade_contract: GradeAxisContract
    metric_version: str
    cluster_count: int
    chi: int
    phi: float
    closure_threshold: float
    leaves: tuple[PlantedLeaf, ...]
    probes: tuple[PlantedProbe, ...]

    def __post_init__(self) -> None:
        _require(bool(self.assumption.strip()) and bool(self.fibre.strip()),
                 "planted world must declare assumption and fibre")
        _require(self.cluster_count >= 2 and self.cluster_count <= len(self.leaves),
                 "planted cluster count is outside the leaf population")
        _require(self.grade_contract.coarse_to_fine == ("cluster", "leaf"),
                 "planted acceptance uses the explicit cluster-to-leaf grade contract")
        _require(len({leaf.logical_id for leaf in self.leaves}) == len(self.leaves),
                 "planted logical leaf ids must be unique")
        _require(len({leaf.object_id for leaf in self.leaves}) == len(self.leaves),
                 "planted leaf object ids must be unique")
        _require(len({leaf.content_handle for leaf in self.leaves}) == len(self.leaves),
                 "planted leaf content handles must be unique")
        dims = {len(leaf.vector) for leaf in self.leaves}
        dims.update(len(probe.query_vector) for probe in self.probes)
        _require(len(dims) == 1, "planted leaves and probes must share one vector dimension")
        leaf_ids = {leaf.logical_id for leaf in self.leaves}
        _require(all(probe.expected_leaf_id in leaf_ids for probe in self.probes),
                 "planted probe expects an unknown leaf")
        _require(bool(self.probes), "planted acceptance needs at least one probe")
        _require(0.0 <= self.closure_threshold <= 1.0,
                 "closure threshold must be in [0, 1]")


@dataclass(frozen=True)
class AcceptanceMetadata:
    occurred_at: str
    producer: SeatRole
    actor: SeatRole
    correlation_id: str
    provenance: tuple[SourceRef, ...]
    runtime: RuntimeReceipt
    producer_ref: ProducerRef


@dataclass(frozen=True)
class RoutedAnswer:
    probe_id: str
    cluster_id: str
    leaf_logical_id: str
    leaf_object_id: str
    source_chain: tuple[str, ...]
    correct_leaf: bool
    complete_source_chain: bool

    @property
    def passed(self) -> bool:
        return self.correct_leaf and self.complete_source_chain


@dataclass(frozen=True)
class BankedAcceptance:
    world: PlantedWorld
    placement: tuple[DerivedCluster, ...]
    cluster_nodes: Mapping[str, CoarseNode]
    promotions: Mapping[str, UpActReceipt]
    promotion_event_ids: Mapping[str, str]
    answers: tuple[RoutedAnswer, ...]
    probe_set_handle: str
    observation_event_id: str
    closure_residual: Residual


@dataclass(frozen=True)
class IncrementalRepair:
    accepted: BankedAcceptance
    affected_cluster_id: str
    previous_node_handle: str
    repaired_node_handle: str
    untouched_cluster_ids: tuple[str, ...]
    untouched_objects_before: Mapping[str, Mapping[str, object]]
    untouched_objects_after: Mapping[str, Mapping[str, object]]


@dataclass(frozen=True)
class TwoAssumptionAcceptance:
    """Two measured fibres, exact UP-face joins, and one caught illicit crossing."""

    first: BankedAcceptance
    second: BankedAcceptance
    first_join_ids: tuple[str, ...]
    second_join_ids: tuple[str, ...]
    transport_event_id: str
    illicit_join_refusal_event_id: str


def derive_placement(
    leaves: Sequence[PlantedLeaf], cluster_count: int
) -> tuple[DerivedCluster, ...]:
    """Compatibility name; the planted bench now fires the production placement organ."""

    return derive_spectral_placement(leaves, cluster_count)


def _up_for_cluster(
    world: PlantedWorld,
    cluster: DerivedCluster,
    leaves: Mapping[str, PlantedLeaf],
) -> tuple[UpInputs, CoarseNode]:
    members = sorted(
        (leaves[logical_id] for logical_id in cluster.member_logical_ids),
        key=lambda leaf: leaf.content_handle,
    )
    inputs = UpInputs(
        world.assumption,
        world.fibre,
        world.grade_contract.axis,
        "leaf",
        "cluster",
        world.metric_version,
        world.grade_contract.contract_id,
        world.chi,
        world.phi,
        world.grade_contract.coarse_to_fine,
        tuple(leaf.child() for leaf in members),
    )
    result = up(inputs)
    assert result.node is not None
    return inputs, result.node


def _route(
    world: PlantedWorld,
    placement: Sequence[DerivedCluster],
    nodes: Mapping[str, CoarseNode],
    leaves: Mapping[str, PlantedLeaf],
) -> tuple[RoutedAnswer, ...]:
    answers = []
    for probe in world.probes:
        cluster = max(
            placement,
            key=lambda item: (
                _cosine(probe.query_vector, nodes[item.cluster_id].centroid),
                item.cluster_id,
            ),
        )
        leaf = max(
            (leaves[logical_id] for logical_id in cluster.member_logical_ids),
            key=lambda item: (
                _cosine(probe.query_vector, item.vector),
                item.logical_id,
            ),
        )
        answers.append(RoutedAnswer(
            probe.probe_id,
            cluster.cluster_id,
            leaf.logical_id,
            leaf.object_id,
            leaf.source_chain,
            leaf.logical_id == probe.expected_leaf_id,
            leaf.source_chain == probe.expected_source_chain,
        ))
    return tuple(answers)


def _control_residual() -> Residual:
    return Residual(
        ResidualStatus.UNKNOWN,
        None,
        None,
        "not-applicable",
        "control/declaration event has no numerical closure claim",
    )


def _event(
    metadata: AcceptanceMetadata,
    kind: EventKind,
    payload: Mapping[str, object],
    *,
    subject: str,
    assumption: str | None,
    fibre: str | None,
    residual: Residual | None = None,
    provenance: tuple[SourceRef, ...] | None = None,
    causation_ids: tuple[str, ...] = (),
) -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at=metadata.occurred_at,
        kind=kind,
        producer=metadata.producer,
        actor=metadata.actor,
        subject=subject,
        assumption=assumption,
        fibre=fibre,
        correlation_id=metadata.correlation_id,
        causation_ids=causation_ids,
        provenance=provenance or metadata.provenance,
        residual=residual or _control_residual(),
        runtime=metadata.runtime,
        producer_ref=metadata.producer_ref,
        validity=Validity.VALID,
        payload=dict(payload),
    )


def _bootstrap(
    store: ConceptricStore, world: PlantedWorld, metadata: AcceptanceMetadata
) -> None:
    state = store.replay()
    if state.lifecycle == LifecyclePhase.SLEEPING:
        store.append(_event(
            metadata,
            EventKind.LIFECYCLE,
            LifecycleTransition(
                LifecycleAction.COLD_WAKE,
                LifecyclePhase.SLEEPING,
                LifecyclePhase.AWAKE,
                "planted-updown-acceptance",
            ).to_dict(),
            subject="lifecycle:planted-updown-acceptance",
            assumption=None,
            fibre=None,
        ))
        state = store.replay()
    if state.active_assumption is None:
        store.append(_event(
            metadata,
            EventKind.ASSUMPTION,
            AssumptionSelection(world.assumption, world.fibre, 1.0, ()).to_dict(),
            subject="assumption:planted-updown-acceptance",
            assumption=world.assumption,
            fibre=world.fibre,
        ))
        state = store.replay()
    _require((state.active_assumption, state.active_fibre) == (world.assumption, world.fibre),
             "planted acceptance cannot cross the store's active assumption fibre")
    existing_contract = state.grade_axis_contracts.get(world.grade_contract.contract_id)
    if existing_contract is None:
        store.append(_event(
            metadata,
            EventKind.GRADE_AXIS,
            world.grade_contract.to_dict(),
            subject=world.grade_contract.contract_id,
            assumption=None,
            fibre=None,
        ))
    else:
        _require(existing_contract == world.grade_contract,
                 "planted acceptance grade contract contradicts the store")


def _declare_leaf(
    store: ConceptricStore,
    world: PlantedWorld,
    metadata: AcceptanceMetadata,
    leaf: PlantedLeaf,
) -> AtlasEvent:
    item = ConceptricObject(
        leaf.object_id,
        "planted-source-leaf",
        leaf.content_handle,
        world.assumption,
        world.fibre,
        world.grade_contract.contract_id,
        "leaf",
        metadata.provenance,
        {
            "logical_id": leaf.logical_id,
            "text": leaf.text,
            "vector": list(leaf.vector),
            "source_chain": list(leaf.source_chain),
        },
    )
    declared = _event(
        metadata,
        EventKind.OBJECT,
        item.to_dict(),
        subject=f"leaf:{leaf.logical_id}",
        assumption=world.assumption,
        fibre=world.fibre,
    )
    store.append(declared)
    return declared


def _probe_evidence(
    store: ConceptricStore,
    world: PlantedWorld,
    metadata: AcceptanceMetadata,
    answers: tuple[RoutedAnswer, ...],
    placement: Sequence[DerivedCluster],
    nodes: Mapping[str, CoarseNode],
    leaves: Mapping[str, PlantedLeaf],
    *,
    causation_ids: tuple[str, ...] = (),
) -> tuple[str, AtlasEvent, Residual, SourceRef]:
    probe_set = GoalClosureProbeSet(
        world.assumption,
        world.fibre,
        EXACT_MEMBER_COVERAGE,
        tuple(
            GoalClosureProbe(
                probe.probe_id,
                probe.question,
                probe.query_vector,
                probe.expected_leaf_id,
                probe.expected_source_chain,
            )
            for probe in world.probes
        ),
    )
    probe_set_handle = probe_set.handle
    probe_item = ConceptricObject(
        f"goal-closure-probe-set:{probe_set_handle}",
        GOAL_CLOSURE_PROBE_SET_KIND,
        probe_set_handle,
        world.assumption,
        world.fibre,
        world.grade_contract.contract_id,
        "leaf",
        metadata.provenance,
        probe_set.to_dict(),
    )
    state = store.replay()
    probe_event_id = state.goal_closure_probe_events.get(probe_set_handle)
    if probe_event_id is None:
        probe_event = _event(
            metadata,
            EventKind.OBJECT,
            probe_item.to_dict(),
            subject=f"goal-closure-probe-set:{probe_set_handle}",
            assumption=world.assumption,
            fibre=world.fibre,
            causation_ids=causation_ids,
        )
        store.append(probe_event)
        probe_event_id = probe_event.event_id
    misses = sum(not answer.passed for answer in answers)
    value = misses / len(answers)
    status = (
        ResidualStatus.WITHIN_BOUND
        if value <= world.closure_threshold
        else ResidualStatus.EXCEEDS_BOUND
    )
    residual = Residual(
        status,
        value,
        world.closure_threshold,
        "goal-closure",
        "fraction of planted questions lacking the exact leaf or complete source chain",
    )
    probe_source = SourceRef(
        "planted-updown-probe-set",
        probe_set_handle,
        f"handle:{probe_set_handle}",
    )
    observation_receipt = GoalClosureObservation(
        probe_set_handle,
        tuple(nodes[cluster.cluster_id].node_handle for cluster in placement),
        tuple(
            GoalClosureRoutingCandidate(
                cluster.cluster_id,
                nodes[cluster.cluster_id].node_handle,
                nodes[cluster.cluster_id].centroid,
                tuple(
                    UpMemberRef(
                        leaves[logical_id].object_id,
                        leaves[logical_id].content_handle,
                    )
                    for logical_id in sorted(
                        cluster.member_logical_ids,
                        key=lambda item: leaves[item].content_handle,
                    )
                ),
            )
            for cluster in placement
        ),
        tuple(
            GoalClosureAnswer(
                answer.probe_id,
                answer.leaf_logical_id,
                answer.source_chain,
                answer.correct_leaf,
                answer.complete_source_chain,
                answer.passed,
            )
            for answer in answers
        ),
    )
    observation = _event(
        metadata,
        EventKind.OBSERVATION,
        observation_receipt.to_dict(),
        subject=f"closure-probes:{probe_set_handle}",
        assumption=world.assumption,
        fibre=world.fibre,
        residual=residual,
        provenance=(*metadata.provenance, probe_source),
        causation_ids=(*causation_ids, probe_event_id),
    )
    store.append(observation)
    return probe_set_handle, observation, residual, probe_source


def bank_planted_world(
    store: ConceptricStore,
    world: PlantedWorld,
    metadata: AcceptanceMetadata,
) -> BankedAcceptance:
    """Derive, probe, and bank a planted two-face world through canonical history."""

    _bootstrap(store, world, metadata)
    leaves = {leaf.logical_id: leaf for leaf in world.leaves}
    leaf_events = tuple(
        _declare_leaf(store, world, metadata, leaf) for leaf in world.leaves
    )
    placement = derive_placement(world.leaves, world.cluster_count)
    inputs_by_cluster: dict[str, UpInputs] = {}
    nodes: dict[str, CoarseNode] = {}
    for cluster in placement:
        inputs, node = _up_for_cluster(world, cluster, leaves)
        inputs_by_cluster[cluster.cluster_id] = inputs
        nodes[cluster.cluster_id] = node
    answers = _route(world, placement, nodes, leaves)
    probe_set, observation, closure, probe_source = _probe_evidence(
        store,
        world,
        metadata,
        answers,
        placement,
        nodes,
        leaves,
        causation_ids=tuple(event.event_id for event in leaf_events),
    )

    promotions: dict[str, UpActReceipt] = {}
    event_ids: dict[str, str] = {}
    for cluster in placement:
        inputs = inputs_by_cluster[cluster.cluster_id]
        result = up(inputs)
        member_objects = {
            leaf.content_handle: leaf.object_id
            for leaf in (leaves[logical_id] for logical_id in cluster.member_logical_ids)
        }
        receipt = bind_up_result(inputs, result, member_objects)
        receipt = replace(
            receipt,
            goal_closure=GoalClosureClaim(
                GoalClosureStatus.MEASURED,
                probe_set,
                observation.event_id,
                chash(observation.payload),
                "planted question-to-leaf routing and complete source-chain assembly measured",
            ),
        )
        promoted = promotion_event(
            receipt,
            occurred_at=metadata.occurred_at,
            producer=metadata.producer,
            actor=metadata.actor,
            correlation_id=metadata.correlation_id,
            provenance=(*metadata.provenance, probe_source),
            runtime=metadata.runtime,
            producer_ref=metadata.producer_ref,
            goal_residual=closure,
            causation_ids=(observation.event_id,),
        )
        store.append(promoted)
        promotions[cluster.cluster_id] = receipt
        event_ids[cluster.cluster_id] = promoted.event_id
    return BankedAcceptance(
        world,
        placement,
        nodes,
        promotions,
        event_ids,
        answers,
        probe_set,
        observation.event_id,
        closure,
    )


def bank_strict_joins(
    store: ConceptricStore,
    accepted: BankedAcceptance,
    metadata: AcceptanceMetadata,
) -> tuple[str, ...]:
    """Join each promoted node only through the exact faces its banked UP act created."""

    state = store.replay()
    join_ids = []
    for cluster in accepted.placement:
        receipt = accepted.promotions[cluster.cluster_id]
        promotion_event_id = accepted.promotion_event_ids[cluster.cluster_id]
        semantic = state.graph_objects[receipt.semantic_object_id]
        spectral = state.graph_objects[receipt.spectral_object_id]
        join_id = derived_join_id(
            receipt.node_handle,
            accepted.world.assumption,
            accepted.world.fibre,
            receipt.semantic_object_id,
            receipt.spectral_object_id,
            receipt.act_handle,
        )
        join = JoinReceipt(
            join_id,
            receipt.node_handle,
            accepted.world.assumption,
            accepted.world.fibre,
            "strict-up-two-face-join/1",
            semantic.content_handle,
            spectral.content_handle,
            metadata.provenance,
            accepted.closure_residual,
            receipt.semantic_object_id,
            receipt.spectral_object_id,
            receipt.act_handle,
        )
        joined = _event(
            metadata,
            EventKind.JOIN,
            join.to_dict(),
            subject=join.join_id,
            assumption=accepted.world.assumption,
            fibre=accepted.world.fibre,
            residual=accepted.closure_residual,
            causation_ids=(promotion_event_id,),
        )
        store.append(joined)
        join_ids.append(join.join_id)
    return tuple(join_ids)


def bank_two_assumption_worlds(
    store: ConceptricStore,
    first_world: PlantedWorld,
    second_world: PlantedWorld,
    transport: TransportReceipt,
    metadata: AcceptanceMetadata,
) -> TwoAssumptionAcceptance:
    """Bank the smallest nontrivial assumption-indexed UP/join/refusal world.

    This remains a planted law gate.  A separate real-corpus gate must use the same history
    doors before S1 can be called material.
    """

    _require(
        (transport.from_assumption, transport.from_fibre)
        == (first_world.assumption, first_world.fibre)
        and (transport.to_assumption, transport.to_fibre)
        == (second_world.assumption, second_world.fibre),
        "two-assumption transport must connect the two exact planted fibres",
    )
    first = bank_planted_world(store, first_world, metadata)
    first_join_ids = bank_strict_joins(store, first, metadata)
    transport_event = _event(
        metadata,
        EventKind.TRANSPORT,
        transport.to_dict(),
        subject=transport.transport_id,
        assumption=second_world.assumption,
        fibre=second_world.fibre,
        causation_ids=tuple(first.promotion_event_ids.values()),
    )
    store.append(transport_event)
    second = bank_planted_world(store, second_world, metadata)
    second_join_ids = bank_strict_joins(store, second, metadata)
    _require(
        set(first_join_ids).isdisjoint(second_join_ids),
        "two assumptions failed to force distinct exact joins",
    )

    first_cluster = first.placement[0]
    first_receipt = first.promotions[first_cluster.cluster_id]
    state = store.replay()
    semantic = state.graph_objects[first_receipt.semantic_object_id]
    spectral = state.graph_objects[first_receipt.spectral_object_id]
    illicit_id = derived_join_id(
        first_receipt.node_handle,
        second_world.assumption,
        second_world.fibre,
        first_receipt.semantic_object_id,
        first_receipt.spectral_object_id,
        first_receipt.act_handle,
    )
    illicit = JoinReceipt(
        illicit_id,
        first_receipt.node_handle,
        second_world.assumption,
        second_world.fibre,
        "illicit-cross-fibre-up-face-join/1",
        semantic.content_handle,
        spectral.content_handle,
        metadata.provenance,
        first.closure_residual,
        first_receipt.semantic_object_id,
        first_receipt.spectral_object_id,
        first_receipt.act_handle,
    )
    illicit_event = _event(
        metadata,
        EventKind.JOIN,
        illicit.to_dict(),
        subject=illicit.join_id,
        assumption=second_world.assumption,
        fibre=second_world.fibre,
        residual=first.closure_residual,
        causation_ids=(
            first.promotion_event_ids[first_cluster.cluster_id],
            transport_event.event_id,
        ),
    )
    try:
        store.append(illicit_event)
    except StateTransitionRefused as exc:
        refusal = _event(
            metadata,
            EventKind.OBSERVATION,
            {
                "schema_version": "atlas.two-assumption-illicit-join-refusal/1",
                "attempt_handle": chash(illicit_event.to_dict()),
                "from_assumption": first_world.assumption,
                "from_fibre": first_world.fibre,
                "active_assumption": second_world.assumption,
                "active_fibre": second_world.fibre,
                "refusal": str(exc),
            },
            subject=f"refusal:{illicit.join_id}",
            assumption=second_world.assumption,
            fibre=second_world.fibre,
            residual=Residual(
                ResidualStatus.WITHIN_BOUND,
                0.0,
                0.0,
                "illicit-cross-fibre-joins",
                "the attempted old-fibre UP-face join was refused before append",
            ),
            causation_ids=(
                first.promotion_event_ids[first_cluster.cluster_id],
                transport_event.event_id,
            ),
        )
        store.append(refusal)
    else:
        raise StateTransitionRefused("illicit cross-fibre strict join was accepted")

    return TwoAssumptionAcceptance(
        first,
        second,
        first_join_ids,
        second_join_ids,
        transport_event.event_id,
        refusal.event_id,
    )


def repair_dirty_leaf(
    store: ConceptricStore,
    accepted: BankedAcceptance,
    replacement: PlantedLeaf,
    metadata: AcceptanceMetadata,
) -> IncrementalRepair:
    """Replace one logical leaf version and recompute only its existing ancestor cluster."""

    world = accepted.world
    previous = {leaf.logical_id: leaf for leaf in world.leaves}
    old = previous.get(replacement.logical_id)
    _require(old is not None, "dirty repair cites an unknown logical leaf")
    assert old is not None
    _require((old.object_id, old.content_handle) !=
             (replacement.object_id, replacement.content_handle),
             "dirty repair must introduce a new immutable leaf version")
    affected = next(
        cluster
        for cluster in accepted.placement
        if replacement.logical_id in cluster.member_logical_ids
    )
    untouched = tuple(
        cluster.cluster_id for cluster in accepted.placement if cluster != affected
    )
    state_before = store.replay()
    untouched_before = {
        cluster_id: state_before.graph_objects[
            accepted.promotions[cluster_id].coarse_object_id
        ].to_dict()
        for cluster_id in untouched
    }

    leaf_event = _declare_leaf(store, world, metadata, replacement)
    previous[replacement.logical_id] = replacement
    updated_world = replace(
        world,
        leaves=tuple(previous[leaf.logical_id] for leaf in world.leaves),
    )
    inputs, node = _up_for_cluster(updated_world, affected, previous)
    updated_nodes = dict(accepted.cluster_nodes)
    updated_nodes[affected.cluster_id] = node
    answers = _route(updated_world, accepted.placement, updated_nodes, previous)
    result = up(inputs)
    probe_set, observation, closure, probe_source = _probe_evidence(
        store,
        updated_world,
        metadata,
        answers,
        accepted.placement,
        updated_nodes,
        previous,
        causation_ids=(leaf_event.event_id,),
    )
    member_objects = {
        previous[logical_id].content_handle: previous[logical_id].object_id
        for logical_id in affected.member_logical_ids
    }
    receipt = bind_up_result(inputs, result, member_objects)
    receipt = replace(
        receipt,
        goal_closure=GoalClosureClaim(
            GoalClosureStatus.MEASURED,
            probe_set,
            observation.event_id,
            chash(observation.payload),
            "dirty-ancestor repair re-ran the planted routing/source-chain probes",
        ),
    )
    promoted = promotion_event(
        receipt,
        occurred_at=metadata.occurred_at,
        producer=metadata.producer,
        actor=metadata.actor,
        correlation_id=metadata.correlation_id,
        provenance=(*metadata.provenance, probe_source),
        runtime=metadata.runtime,
        producer_ref=metadata.producer_ref,
        goal_residual=closure,
        causation_ids=(
            observation.event_id,
            accepted.promotion_event_ids[affected.cluster_id],
        ),
    )
    store.append(promoted)
    state_after = store.replay()
    untouched_after = {
        cluster_id: state_after.graph_objects[
            accepted.promotions[cluster_id].coarse_object_id
        ].to_dict()
        for cluster_id in untouched
    }
    updated_promotions = dict(accepted.promotions)
    updated_promotions[affected.cluster_id] = receipt
    updated_event_ids = dict(accepted.promotion_event_ids)
    updated_event_ids[affected.cluster_id] = promoted.event_id
    repaired = BankedAcceptance(
        updated_world,
        accepted.placement,
        updated_nodes,
        updated_promotions,
        updated_event_ids,
        answers,
        probe_set,
        observation.event_id,
        closure,
    )
    return IncrementalRepair(
        repaired,
        affected.cluster_id,
        accepted.promotions[affected.cluster_id].node_handle,
        receipt.node_handle,
        untouched,
        untouched_before,
        untouched_after,
    )


__all__ = [
    "AcceptanceMetadata",
    "BankedAcceptance",
    "DerivedCluster",
    "IncrementalRepair",
    "PlantedLeaf",
    "PlantedProbe",
    "PlantedWorld",
    "RoutedAnswer",
    "bank_planted_world",
    "derive_placement",
    "repair_dirty_leaf",
]
