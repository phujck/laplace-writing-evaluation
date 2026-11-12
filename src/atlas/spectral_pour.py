"""The causal S1 pour: persist the spectral map while content enters the Atlas.

This is an organ on the canonical write path, not a post-hoc corpus script.  Its input is the
smallest honest boundary between ingestion and geometry: immutable content-bearing leaves with
already-observed vectors.  One atomic packet then declares those leaves, promotes each derived
block through the pure UP kernel, persists both faces and the complete retained frame, and banks
the measured truncation margin.  Goal closure remains explicitly unmeasured; representation
energy is never promoted into a retrieval claim.

Recursive placement lifts the measured engine stopping law across the sealed package boundary.
Every grade uses the same container operator with explicit fibre dials; refused cuts and safety
floors remain in the tree receipt. Automatic dial selection is not claimed.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar, Mapping, Protocol, Sequence

import numpy as np

from .encoders.base import EncoderRuntimeEvidence, EncoderSpec
from .errors import SchemaFieldMissing, SchemaVersionMismatch, StateTransitionRefused
from .history import (
    AssumptionSelection,
    AtlasEvent,
    ConceptricObject,
    EventKind,
    GradeAxisContract,
    LifecycleAction,
    LifecyclePhase,
    LifecycleTransition,
    ProducerRef,
    Residual,
    ResidualStatus,
    RuntimeReceipt,
    SeatRole,
    SourceRef,
    Validity,
)
from .ids import chash, hash_bytes
from .schema import SemanticAtom
from .store import ConceptricStore
from .updown import ChildLeaf, CoarseNode, UpInputs, up
from .updown_history import UpActReceipt, bind_up_result, derived_cluster_id, promotion_event


def _require(condition: bool, message: str, **fields: object) -> None:
    if not condition:
        raise StateTransitionRefused(message, **fields)


def _require_exact(raw: Mapping[str, Any], keys: tuple[str, ...], where: str) -> None:
    expected = {"schema_version", *keys}
    missing = sorted(expected - set(raw))
    extra = sorted(set(raw) - expected)
    if missing or extra:
        raise SchemaFieldMissing(
            f"{where} fields do not match its schema", fields=missing, unexpected=extra
        )


class ClusterableLeaf(Protocol):
    logical_id: str
    content_handle: str
    vector: tuple[float, ...]


@dataclass(frozen=True)
class SpectralCluster:
    cluster_id: str
    member_logical_ids: tuple[str, ...]
    children: tuple["SpectralCluster", ...] = ()
    depth: int = 1
    stop_reason: str | None = None
    overflow: int = 0

    def walk(self):
        for child in self.children:
            yield from child.walk()
        yield self

    def to_dict(self):
        return dict(cluster_id=self.cluster_id, member_logical_ids=list(self.member_logical_ids),
                    depth=self.depth, stop_reason=self.stop_reason, held=len(self.member_logical_ids),
                    overflow=self.overflow,
                    stop_kind=("safety" if self.stop_reason == "depth_cap" else
                               "leaf_target" if self.stop_reason == "leaf_max" else
                               "cut_decline" if self.stop_reason else None),
                    children=[child.to_dict() for child in self.children])


def _distance2(left: Sequence[float], right: Sequence[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))


def recursive_split_stop(n, depth, *, leaf_max, max_depth, indistinguishable=False,
                         chosen_k=None, distinct_labels=None):
    """Sealed lift of meaning_upfold's measured _resplit_into stopping law.

    A depth cap is safety residue, never a refused cut. Keep both copies equivalent
    with the cross-boundary law test; neither package imports the other.
    """
    if n <= leaf_max:
        return "leaf_max"
    if indistinguishable:
        return "indistinguishable_members"
    if depth >= max_depth:
        return "depth_cap"
    if chosen_k is not None and chosen_k < 2:
        return "silhouette_refused"
    if distinct_labels is not None and distinct_labels < 2:
        return "chosen_k_collapsed"
    return None


RAW_EMBEDDING_KMEANS = "raw-embedding-kmeans/1"
COSINE_AFFINITY_SPECTRAL = "cosine-affinity-spectral-fixed-k/1"
DENSE_SPECTRAL_PLACEMENT_CAP = 2048


def _semantic_kmeans(
    ordered: Sequence[ClusterableLeaf],
    coordinates: Sequence[Sequence[float]],
    cluster_count: int,
) -> tuple[int, ...]:
    """Deterministic Lloyd discretizer; content handles break exact geometric ties only."""

    rows = tuple(tuple(float(value) for value in row) for row in coordinates)
    dimensions = {len(row) for row in rows}
    _require(dimensions != {0} and len(dimensions) == 1,
             "placement coordinates must share one dimension")
    global_centroid = tuple(
        sum(row[dimension] for row in rows) / len(rows)
        for dimension in range(next(iter(dimensions)))
    )
    first_index = max(
        range(len(rows)),
        key=lambda index: (
            _distance2(rows[index], global_centroid),
            ordered[index].content_handle,
        ),
    )
    seed_indices = [first_index]
    while len(seed_indices) < cluster_count:
        candidates = [index for index in range(len(rows)) if index not in seed_indices]
        chosen = max(
            candidates,
            key=lambda index: (
                min(_distance2(rows[index], rows[seed]) for seed in seed_indices),
                ordered[index].content_handle,
            ),
        )
        seed_indices.append(chosen)

    assignments: tuple[int, ...] = ()
    centroids = [rows[index] for index in seed_indices]
    for _ in range(32):
        next_assignments = tuple(
            min(
                range(cluster_count),
                key=lambda index: (_distance2(row, centroids[index]), index),
            )
            for row in rows
        )
        _require(
            len(set(next_assignments)) == cluster_count,
            "semantic placement produced an empty cluster",
        )
        if next_assignments == assignments:
            return next_assignments
        assignments = next_assignments
        centroids = []
        for index in range(cluster_count):
            members = [
                row for row, assigned in zip(rows, assignments, strict=True)
                if assigned == index
            ]
            centroids.append(tuple(
                sum(row[dimension] for row in members) / len(members)
                for dimension in range(len(members[0]))
            ))
    return assignments


def _spectral_coordinates(
    ordered: Sequence[ClusterableLeaf], cluster_count: int
) -> tuple[tuple[float, ...], ...]:
    """Bounded dense cosine-affinity embedding; sparse Lanczos is the scale successor."""

    _require(
        len(ordered) <= DENSE_SPECTRAL_PLACEMENT_CAP,
        "dense spectral placement exceeds its declared cap; sparse operator required",
        leaves=len(ordered),
        cap=DENSE_SPECTRAL_PLACEMENT_CAP,
    )
    xp = np
    if os.environ.get("LAPLACE_REQUIRE_GPU") == "1":
        from .runtime import preload_cuda_libraries
        preload_cuda_libraries()
        try:
            import cupy as xp
            _require(xp.cuda.runtime.getDeviceCount() > 0, "GPU_REQUIRED")
        except Exception as exc:
            raise StateTransitionRefused("GPU_REQUIRED: spectral placement unavailable") from exc
    vectors = xp.asarray([leaf.vector for leaf in ordered], dtype=xp.float64)
    norms = xp.clip(xp.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)
    vectors = vectors / norms
    affinity = xp.clip((vectors @ vectors.T + 1.0) / 2.0, 0.0, 1.0)
    xp.fill_diagonal(affinity, 1.0)
    degrees = xp.clip(affinity.sum(axis=1), 1e-12, None)
    normalized = affinity / xp.sqrt(degrees[:, None] * degrees[None, :])
    _values, eigenvectors = xp.linalg.eigh(normalized)
    coordinates = eigenvectors[:, -cluster_count:][:, ::-1]
    coordinate_norms = xp.clip(
        xp.linalg.norm(coordinates, axis=1, keepdims=True), 1e-12, None
    )
    coordinates = coordinates / coordinate_norms
    if xp is not np:
        coordinates = xp.asnumpy(coordinates)
    return tuple(tuple(float(value) for value in row) for row in coordinates)


def derive_spectral_placement(
    leaves: Sequence[ClusterableLeaf],
    cluster_count: int,
    operator_version: str = COSINE_AFFINITY_SPECTRAL,
) -> tuple[SpectralCluster, ...]:
    """Fibre-local semantic placement with an explicit, replaceable lens."""

    ordered = sorted(leaves, key=lambda leaf: leaf.content_handle)
    _require(1 <= cluster_count <= len(ordered), "invalid spectral cluster count")
    dimensions = {len(leaf.vector) for leaf in ordered}
    _require(dimensions != {0} and len(dimensions) == 1, "pour vectors must share one dimension")
    _require(
        all(math.isfinite(value) for leaf in ordered for value in leaf.vector),
        "pour vectors must be finite",
    )
    if operator_version == COSINE_AFFINITY_SPECTRAL:
        coordinates = _spectral_coordinates(ordered, cluster_count)
    elif operator_version == RAW_EMBEDDING_KMEANS:
        coordinates = tuple(leaf.vector for leaf in ordered)
    else:
        raise StateTransitionRefused(
            "spectral placement operator is unknown", operator_version=operator_version
        )
    assignments = _semantic_kmeans(ordered, coordinates, cluster_count)

    member_sets = [
        tuple(
            sorted(
                leaf.logical_id
                for leaf, assigned in zip(ordered, assignments, strict=True)
                if assigned == index
            )
        )
        for index in range(cluster_count)
    ]
    member_sets.sort()
    return tuple(
        SpectralCluster(derived_cluster_id(members), members) for members in member_sets
    )


@dataclass(frozen=True)
class PourLeaf:
    logical_id: str
    object_id: str
    content_handle: str
    text: str
    vector: tuple[float, ...]
    source_chain: tuple[str, ...]
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("logical_id", "object_id", "content_handle", "text"):
            _require(bool(str(getattr(self, field_name)).strip()), "pour leaf field is empty")
        _require(bool(self.vector), "pour leaf vector is empty")
        _require(bool(self.source_chain) and all(self.source_chain), "source chain is empty")
        _require(
            not ({"logical_id", "text", "vector", "source_chain"} & set(self.attributes)),
            "pour leaf attributes cannot override the canonical leaf fields",
        )

    def child(self) -> ChildLeaf:
        return ChildLeaf(self.content_handle, self.text, self.vector)


def observed_pour_leaf(
    atom: SemanticAtom,
    *,
    logical_id: str,
    object_id: str,
    vector: Sequence[float],
    attributes: Mapping[str, Any] | None = None,
) -> PourLeaf:
    """Bind one exact observed atom to the lower-level spectral leaf mechanism.

    This pure adapter establishes observation custody; ``bank_spectral_pour`` remains usable for
    explicitly planted/synthetic leaves and does not acquire an observation claim by itself.
    """

    _require(atom.atom_id == atom.computed_id(), "semantic atom identity does not reproduce")
    _require(
        hash_bytes(atom.content_utf8.encode("utf-8")) == atom.content_handle,
        "semantic atom content handle does not reproduce",
    )
    carried = {
        "observation_channel": "atlas.semantic-observation/1",
        "atom_id": atom.atom_id,
        "snapshot_id": atom.snapshot_id,
        "generation_id": atom.generation_id,
        "node_id": atom.node_id,
        "path": atom.path,
        "span_id": atom.span_id,
        "start": atom.start,
        "end": atom.end,
    }
    supplied = dict(attributes or {})
    _require(not (set(carried) & set(supplied)), "observed leaf attributes override atom custody")
    return PourLeaf(
        logical_id=logical_id,
        object_id=object_id,
        content_handle=atom.content_handle,
        text=atom.content_utf8,
        vector=tuple(float(value) for value in vector),
        source_chain=(
            atom.snapshot_id, atom.generation_id, atom.node_id, atom.span_id,
            atom.atom_id, atom.content_handle,
        ),
        attributes={**carried, **supplied},
    )


@dataclass(frozen=True)
class SpectralPourContract:
    assumption: str
    fibre: str
    grade_contract: GradeAxisContract
    lens_id: str
    encoder_spec: EncoderSpec
    metric_version: str
    cluster_count: int
    chi: int
    phi: float
    placement_operator: str = COSINE_AFFINITY_SPECTRAL
    leaf_max: int | None = None
    branching: int | tuple[int, ...] | None = None
    max_depth: int | None = None
    grade_chi: tuple[int, ...] = ()
    grade_phi: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        _require(bool(self.assumption.strip()) and bool(self.fibre.strip()), "pour fibre is empty")
        _require(bool(self.lens_id.strip()), "pour lens id is empty")
        _require(bool(self.metric_version.strip()), "pour metric version is empty")
        _require(
            self.placement_operator in {COSINE_AFFINITY_SPECTRAL, RAW_EMBEDDING_KMEANS},
            "pour placement operator is unknown",
            placement_operator=self.placement_operator,
        )
        _require(
            len(self.grade_contract.coarse_to_fine) >= 2
            and self.grade_contract.coarse_to_fine[-1] == "leaf",
            "spectral pour needs a declared chain ending at leaf",
        )
        _require(self.cluster_count >= 1, "spectral pour needs at least one cluster")
        _require(isinstance(self.chi, int) and not isinstance(self.chi, bool) and self.chi >= 1,
                 "chi must be an explicit positive integer")
        _require(math.isfinite(self.phi) and 0.0 < self.phi <= 1.0,
                 "phi must be an explicit value in (0, 1]")

        if self.leaf_max is not None:
            _require(type(self.leaf_max) is int and self.leaf_max >= 1,
                     "leaf_max must be a positive integer")
            _require(type(self.max_depth) is int and self.max_depth >= 1,
                     "recursive pour requires max_depth safety dial")
            branches = self.branching if isinstance(self.branching, tuple) else (self.branching,)
            _require(all(type(b) is int and b >= 2 for b in branches),
                     "recursive pour requires branching dials >= 2")
            _require(len(branches) == 1 or len(branches) == self.max_depth - 1,
                     "branching must cover every recursive cut")
            _require(len(self.grade_contract.coarse_to_fine) == self.max_depth + 1,
                     "grade chain must cover the safety depth")
            _require(not self.grade_chi or (len(self.grade_chi) == self.max_depth
                     and all(type(v) is int and v >= 1 for v in self.grade_chi)), "invalid grade chi")
            _require(not self.grade_phi or (len(self.grade_phi) == self.max_depth
                     and all(math.isfinite(v) and 0 < v <= 1 for v in self.grade_phi)), "invalid grade phi")
        else:
            _require(self.max_depth is None and self.branching is None
                     and not self.grade_chi and not self.grade_phi
                     and len(self.grade_contract.coarse_to_fine) == 2,
                     "recursive pour requires explicit leaf_max, branching and max_depth")

    @property
    def encoder_version(self) -> str:
        """Compatibility spelling for consumers that mean the complete encoder spec."""
        return self.encoder_spec.spec_id

    @property
    def vector_space_id(self) -> str:
        """Smallest domain in which raw vector comparison is licensed."""
        return chash({
            "schema_version": "atlas.vector-space/1",
            "assumption": self.assumption,
            "fibre": self.fibre,
            "grade_axis_contract_id": self.grade_contract.contract_id,
            "lens_id": self.lens_id,
            "encoder_spec_id": self.encoder_spec.spec_id,
            "metric_version": self.metric_version,
        })

    @property
    def contract_handle(self) -> str:
        return chash({
            "schema_version": "atlas.spectral-pour-contract/4",
            "assumption": self.assumption,
            "fibre": self.fibre,
            "grade_contract": self.grade_contract.to_dict(),
            "lens_id": self.lens_id,
            "encoder_spec": self.encoder_spec.to_dict(),
            "metric_version": self.metric_version,
            "vector_space_id": self.vector_space_id,
            "cluster_count": self.cluster_count,
            "chi": self.chi,
            "phi": self.phi,
            "placement_operator": self.placement_operator,
            "leaf_max": self.leaf_max, "branching": self.branching,
            "max_depth": self.max_depth, "grade_chi": self.grade_chi,
            "grade_phi": self.grade_phi,
        })


@dataclass(frozen=True)
class PourMetadata:
    occurred_at: str
    producer: SeatRole
    actor: SeatRole
    correlation_id: str
    provenance: tuple[SourceRef, ...]
    runtime: RuntimeReceipt
    producer_ref: ProducerRef
    encoder_runtime_evidence: EncoderRuntimeEvidence | None = None


@dataclass(frozen=True)
class SpectralMargin:
    SCHEMA_VERSION: ClassVar[str] = "atlas.spectral-margin/1"

    cluster_id: str
    promotion_event_id: str
    node_handle: str
    truncation_residual: float
    phi: float
    signed_margin: float
    degenerate_cut: bool
    representation_sufficient: bool
    forced_descent: bool

    def __post_init__(self) -> None:
        _require(
            math.isclose(self.signed_margin, self.phi - self.truncation_residual, abs_tol=1e-12),
            "spectral margin does not equal phi minus truncation residual",
        )
        _require(
            self.representation_sufficient
            == (self.signed_margin >= -1e-12 and not self.degenerate_cut),
            "spectral margin contradicts representation sufficiency",
        )
        _require(self.forced_descent == (not self.representation_sufficient),
                 "spectral margin contradicts forced descent")

    @property
    def status(self) -> str:
        return "within-bound" if self.representation_sufficient else "descent-required"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "cluster_id": self.cluster_id,
            "promotion_event_id": self.promotion_event_id,
            "node_handle": self.node_handle,
            "truncation_residual": self.truncation_residual,
            "phi": self.phi,
            "signed_margin": self.signed_margin,
            "degenerate_cut": self.degenerate_cut,
            "representation_sufficient": self.representation_sufficient,
            "forced_descent": self.forced_descent,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SpectralMargin":
        _require_exact(raw, (
            "cluster_id", "promotion_event_id", "node_handle", "truncation_residual",
            "phi", "signed_margin", "degenerate_cut", "representation_sufficient",
            "forced_descent", "status",
        ), "SpectralMargin")
        if raw["schema_version"] != cls.SCHEMA_VERSION:
            raise SchemaVersionMismatch(
                "SpectralMargin schema is unknown", expected=cls.SCHEMA_VERSION,
                got=raw["schema_version"],
            )
        result = cls(
            raw["cluster_id"], raw["promotion_event_id"], raw["node_handle"],
            float(raw["truncation_residual"]), float(raw["phi"]),
            float(raw["signed_margin"]), bool(raw["degenerate_cut"]),
            bool(raw["representation_sufficient"]), bool(raw["forced_descent"]),
        )
        _require(raw["status"] == result.status, "stored spectral margin status is false")
        return result


@dataclass(frozen=True)
class SpectralPourReceipt:
    SCHEMA_VERSION: ClassVar[str] = "atlas.spectral-pour-receipt/3"

    pour_handle: str
    contract_handle: str
    placement_operator: str
    mode: str
    parent_pour_handle: str | None
    leaf_object_ids: tuple[str, ...]
    placement: tuple[SpectralCluster, ...]
    margins: tuple[SpectralMargin, ...]
    touched_cluster_ids: tuple[str, ...]
    untouched_node_handles: tuple[str, ...]
    depth_policy: Mapping[str, Any] | None = None

    def hashed_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "contract_handle": self.contract_handle,
            "placement_operator": self.placement_operator,
            "mode": self.mode,
            "parent_pour_handle": self.parent_pour_handle,
            "leaf_object_ids": list(self.leaf_object_ids),
            "placement": [
                item.to_dict() for item in self.placement
            ],
            "margins": [item.to_dict() for item in self.margins],
            "touched_cluster_ids": list(self.touched_cluster_ids),
            "untouched_node_handles": list(self.untouched_node_handles),
            "depth_policy": dict(self.depth_policy) if self.depth_policy is not None else None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.hashed_dict(), "pour_handle": self.pour_handle}

    @classmethod
    def create(cls, **fields: Any) -> "SpectralPourReceipt":
        draft = cls(pour_handle="", **fields)
        return replace(draft, pour_handle=chash(draft.hashed_dict()))


@dataclass(frozen=True)
class BankedSpectralPour:
    contract: SpectralPourContract
    leaves: tuple[PourLeaf, ...]
    receipt: SpectralPourReceipt
    observation_event_id: str
    promotions: Mapping[str, UpActReceipt]
    promotion_event_ids: Mapping[str, str]
    nodes: Mapping[str, CoarseNode]


def _control_residual() -> Residual:
    return Residual(
        ResidualStatus.UNKNOWN,
        None,
        None,
        "not-applicable",
        "control/declaration event makes no numerical closure claim",
    )


def _unknown_goal_closure() -> Residual:
    return Residual(
        ResidualStatus.UNKNOWN,
        None,
        None,
        "goal-closure",
        "spectral pour prices representation only; goal closure needs a separate probe event",
    )


def _event(
    metadata: PourMetadata,
    kind: EventKind,
    payload: Mapping[str, object],
    *,
    subject: str,
    assumption: str | None,
    fibre: str | None,
    residual: Residual | None = None,
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
        provenance=metadata.provenance,
        residual=residual or _control_residual(),
        runtime=metadata.runtime,
        producer_ref=metadata.producer_ref,
        validity=Validity.VALID,
        payload=dict(payload),
    )


def _bootstrap_events(
    store: ConceptricStore, contract: SpectralPourContract, metadata: PourMetadata
) -> list[AtlasEvent]:
    state = store.replay()
    events: list[AtlasEvent] = []
    if state.lifecycle == LifecyclePhase.SLEEPING:
        events.append(_event(
            metadata,
            EventKind.LIFECYCLE,
            LifecycleTransition(
                LifecycleAction.COLD_WAKE,
                LifecyclePhase.SLEEPING,
                LifecyclePhase.AWAKE,
                "spectral-pour",
            ).to_dict(),
            subject="lifecycle:spectral-pour",
            assumption=None,
            fibre=None,
        ))
    if state.active_assumption is None:
        events.append(_event(
            metadata,
            EventKind.ASSUMPTION,
            AssumptionSelection(contract.assumption, contract.fibre, 1.0, ()).to_dict(),
            subject=f"assumption:{contract.contract_handle}",
            assumption=contract.assumption,
            fibre=contract.fibre,
        ))
    else:
        _require(
            (state.active_assumption, state.active_fibre)
            == (contract.assumption, contract.fibre),
            "spectral pour cannot cross the active assumption fibre without transport",
        )
    existing_contract = state.grade_axis_contracts.get(contract.grade_contract.contract_id)
    if existing_contract is None:
        events.append(_event(
            metadata,
            EventKind.GRADE_AXIS,
            contract.grade_contract.to_dict(),
            subject=contract.grade_contract.contract_id,
            assumption=None,
            fibre=None,
        ))
    else:
        _require(existing_contract == contract.grade_contract,
                 "spectral pour grade contract contradicts the store")
    return events


def _leaf_object(
    leaf: PourLeaf, contract: SpectralPourContract, metadata: PourMetadata
) -> ConceptricObject:
    return ConceptricObject(
        leaf.object_id,
        "source-leaf",
        leaf.content_handle,
        contract.assumption,
        contract.fibre,
        contract.grade_contract.contract_id,
        "leaf",
        metadata.provenance,
        {
            "logical_id": leaf.logical_id,
            "text": leaf.text,
            "vector": list(leaf.vector),
            "lens_id": contract.lens_id,
            "encoder_spec": contract.encoder_spec.to_dict(),
            "encoder_version": contract.encoder_version,
            "metric_version": contract.metric_version,
            "vector_space_id": contract.vector_space_id,
            "source_chain": list(leaf.source_chain),
            **dict(leaf.attributes),
        },
    )


def _promote_cluster(
    cluster: SpectralCluster,
    leaves: Mapping[str, PourLeaf],
    contract: SpectralPourContract,
) -> tuple[CoarseNode, UpActReceipt]:
    members = tuple(
        leaves[logical_id]
        for logical_id in sorted(
            (tuple(child.cluster_id for child in cluster.children) if cluster.children
             else cluster.member_logical_ids), key=lambda item: leaves[item].content_handle
        )
    )
    from_grade = (contract.grade_contract.coarse_to_fine[cluster.depth]
                  if cluster.children else "leaf")
    to_grade = contract.grade_contract.coarse_to_fine[cluster.depth - 1]
    chi = contract.grade_chi[cluster.depth - 1] if contract.grade_chi else contract.chi
    phi = contract.grade_phi[cluster.depth - 1] if contract.grade_phi else contract.phi
    inputs = UpInputs(
        contract.assumption, contract.fibre, contract.grade_contract.axis,
        from_grade, to_grade, contract.vector_space_id, contract.grade_contract.contract_id,
        min(chi, max(1, len(members) - 1)), phi,
        contract.grade_contract.coarse_to_fine, tuple(item.child() for item in members),
    )
    result = up(inputs)
    receipt = bind_up_result(inputs, result,
                             {item.content_handle: item.object_id for item in members})
    return result.node, receipt


def _margin(
    cluster_id: str, promotion: AtlasEvent, receipt: UpActReceipt
) -> SpectralMargin:
    residual = receipt.frame.truncation_residual
    return SpectralMargin(
        cluster_id,
        promotion.event_id,
        receipt.node_handle,
        residual,
        receipt.phi,
        receipt.phi - residual,
        receipt.frame.degenerate_cut,
        receipt.representation_sufficient,
        not receipt.representation_sufficient,
    )


def _same_up_transform(
    existing: UpActReceipt, candidate: UpActReceipt
) -> bool:
    """Recognize one pure UP result rebound to equivalent contextual leaf addresses."""

    if tuple(member.content_handle for member in existing.members) != tuple(
        member.content_handle for member in candidate.members
    ):
        return False
    return replace(existing, members=candidate.members) == candidate


def derive_recursive_placement(leaves, contract):
    if contract.leaf_max is not None and leaves and all(leaf.vector == leaves[0].vector for leaf in leaves):
        roots = (SpectralCluster(derived_cluster_id([leaf.logical_id for leaf in leaves]),
                                 tuple(sorted(leaf.logical_id for leaf in leaves))),)
    else:
        roots = derive_spectral_placement(leaves, contract.cluster_count, contract.placement_operator)
    if contract.leaf_max is None:
        return roots
    by_id = {leaf.logical_id: leaf for leaf in leaves}

    def descend(cluster, depth):
        members = [by_id[key] for key in cluster.member_logical_ids]
        reason = recursive_split_stop(len(members), depth, leaf_max=contract.leaf_max,
            max_depth=contract.max_depth,
            indistinguishable=all(m.vector == members[0].vector for m in members))
        children = ()
        if reason is None:
            branches = contract.branching
            k = branches[min(depth - 1, len(branches) - 1)] if isinstance(branches, tuple) else branches
            k = min(k, len(members) - 1)
            try:
                cut = derive_spectral_placement(members, k, contract.placement_operator)
            except StateTransitionRefused as exc:
                if "empty cluster" not in str(exc):
                    raise
                cut = ()
            reason = recursive_split_stop(len(members), depth, leaf_max=contract.leaf_max,
                max_depth=contract.max_depth, chosen_k=k, distinct_labels=len(cut))
            if reason is None:
                children = tuple(descend(c, depth + 1) for c in cut)
        return replace(cluster, depth=depth, children=children, stop_reason=reason,
                       overflow=max(0, len(members) - contract.leaf_max) if reason else 0)
    return tuple(descend(root, 1) for root in roots)


def bank_spectral_pour(
    store: ConceptricStore,
    contract: SpectralPourContract,
    leaves: Sequence[PourLeaf],
    metadata: PourMetadata,
    *,
    placement: tuple[SpectralCluster, ...] | None = None,
) -> BankedSpectralPour:
    """Persist the complete bottom-up tree in one atomic packet.

    Explicit placement freezes membership for propagation checks and repair callers.
    """

    leaves = tuple(leaves)
    _require(contract.cluster_count <= len(leaves), "cluster count exceeds leaf count")
    _require(len({leaf.logical_id for leaf in leaves}) == len(leaves),
             "pour logical ids must be unique")
    _require(len({leaf.object_id for leaf in leaves}) == len(leaves),
             "pour object ids must be unique")
    _require(len({leaf.content_handle for leaf in leaves}) == len(leaves),
             "pour content handles must be unique")
    placement = placement if placement is not None else derive_recursive_placement(leaves, contract)
    _require(sorted(key for root in placement for key in root.member_logical_ids)
             == sorted(leaf.logical_id for leaf in leaves), "placement must partition the leaves")
    seen_clusters = set()
    def validate_tree(node):
        _require(node.cluster_id == derived_cluster_id(node.member_logical_ids)
                 and node.cluster_id not in seen_clusters, "invalid or repeated cluster identity")
        seen_clusters.add(node.cluster_id)
        _require(node.depth <= len(contract.grade_contract.coarse_to_fine) - 1,
                 "placement exceeds grade contract")
        if node.children:
            _require(sorted(k for c in node.children for k in c.member_logical_ids)
                     == sorted(node.member_logical_ids), "child partition contradicts parent")
            for child in node.children:
                _require(child.depth == node.depth + 1, "child grade is not adjacent")
                validate_tree(child)
    for root in placement:
        _require(root.depth == 1, "root must be grade 1")
        validate_tree(root)
    by_logical_id = {leaf.logical_id: leaf for leaf in leaves}
    state = store.replay()
    stored_events = {event.event_id: event for event in store.events()}
    stored_event_ids = set(stored_events)
    events = _bootstrap_events(store, contract, metadata)
    leaf_event_ids: list[str] = []
    leaf_events_by_logical_id: dict[str, str] = {}
    for leaf in leaves:
        item = _leaf_object(leaf, contract, metadata)
        existing = state.graph_objects.get(item.object_id)
        if existing is not None:
            _require(existing == item, "pour leaf object id resolves to different content")
            continue
        declared = _event(
            metadata,
            EventKind.OBJECT,
            item.to_dict(),
            subject=f"leaf:{leaf.logical_id}",
            assumption=contract.assumption,
            fibre=contract.fibre,
        )
        events.append(declared)
        leaf_event_ids.append(declared.event_id)
        leaf_events_by_logical_id[leaf.logical_id] = declared.event_id

    nodes: dict[str, CoarseNode] = {}
    promotions: dict[str, UpActReceipt] = {}
    promotion_events: dict[str, AtlasEvent] = {}
    margins: list[SpectralMargin] = []
    for cluster in (node for root in placement for node in root.walk()):
        node, receipt = _promote_cluster(cluster, by_logical_id, contract)
        existing_receipt = state.up_acts.get(receipt.act_handle)
        if existing_receipt is not None:
            _require(
                _same_up_transform(existing_receipt, receipt),
                "stored UP act handle contradicts the recomputed spectral frame",
            )
            # The act handle names the pure transform over immutable content handles.  A
            # storage/schema migration may give those same versions new contextual object ids;
            # reuse the first exact receipt rather than pretending the mathematics changed.
            receipt = existing_receipt
            existing_event_id = next(
                event_id for event_id, act_handle in state.up_events.items()
                if act_handle == receipt.act_handle
            )
            promoted = stored_events[existing_event_id]
        else:
            promoted = promotion_event(
                receipt,
                occurred_at=metadata.occurred_at,
                producer=metadata.producer,
                actor=metadata.actor,
                correlation_id=metadata.correlation_id,
                provenance=metadata.provenance,
                runtime=metadata.runtime,
                producer_ref=metadata.producer_ref,
                goal_residual=_unknown_goal_closure(),
                causation_ids=(tuple(promotion_events[child.cluster_id].event_id
                                     for child in cluster.children) if cluster.children else tuple(
                    leaf_events_by_logical_id[logical_id]
                    for logical_id in cluster.member_logical_ids
                    if logical_id in leaf_events_by_logical_id
                )),
            )
        by_logical_id[cluster.cluster_id] = PourLeaf(
            cluster.cluster_id, receipt.coarse_object_id, node.node_handle,
            node.semantic_face, node.centroid, (node.node_handle,))
        nodes[cluster.cluster_id] = node
        promotions[cluster.cluster_id] = receipt
        promotion_events[cluster.cluster_id] = promoted
        margins.append(_margin(cluster.cluster_id, promoted, receipt))
        if existing_receipt is None and promoted.event_id not in stored_event_ids:
            events.append(promoted)

    receipt = SpectralPourReceipt.create(
        contract_handle=contract.contract_handle,
        placement_operator=contract.placement_operator,
        mode="initial",
        parent_pour_handle=None,
        leaf_object_ids=tuple(sorted(leaf.object_id for leaf in leaves)),
        placement=placement,
        margins=tuple(margins),
        touched_cluster_ids=tuple(node.cluster_id for root in placement for node in root.walk()),
        untouched_node_handles=(),
        depth_policy=(dict(leaf_max=contract.leaf_max, branching=contract.branching,
                           max_depth=contract.max_depth, chi=contract.chi, phi=contract.phi,
                           grade_chi=contract.grade_chi, grade_phi=contract.grade_phi,
                           stop_law="measured-resplit-into/1") if contract.leaf_max is not None else None),
    )
    worst = max(margin.truncation_residual for margin in margins)
    observation = _event(
        metadata,
        EventKind.OBSERVATION,
        receipt.to_dict(),
        subject=receipt.pour_handle,
        assumption=contract.assumption,
        fibre=contract.fibre,
        residual=Residual(
            ResidualStatus.WITHIN_BOUND if all(
                margin.representation_sufficient for margin in margins
            ) else ResidualStatus.EXCEEDS_BOUND,
            worst,
            contract.phi,
            "discarded-spectral-energy-share",
            "worst block at this pour; goal closure is deliberately not implied",
        ),
        causation_ids=tuple(event.event_id for event in promotion_events.values()),
    )
    if observation.event_id not in stored_event_ids:
        events.append(observation)
    store.append_many(events)
    return BankedSpectralPour(
        contract,
        leaves,
        receipt,
        observation.event_id,
        promotions,
        {cluster_id: event.event_id for cluster_id, event in promotion_events.items()},
        nodes,
    )


def repair_spectral_pour(
    store: ConceptricStore,
    banked: BankedSpectralPour,
    replacement: PourLeaf,
    metadata: PourMetadata,
) -> BankedSpectralPour:
    """Repair one dirty leaf's existing ancestor and preserve every untouched frame exactly.

    This first incremental operator deliberately keeps the previous placement.  Repartitioning
    is a different, wider act because it can dirty sibling ancestry; the standing crutch row
    makes the crossover trigger explicit.  Within the licensed local act, both the new immutable
    leaf version and its replacement frame/margin bank atomically.
    """

    _require(banked.contract.leaf_max is None,
             "RECURSIVE_REPAIR_REQUIRED: single-ancestor repair cannot consume a recursive pour")
    previous = {leaf.logical_id: leaf for leaf in banked.leaves}
    old = previous.get(replacement.logical_id)
    _require(old is not None, "spectral repair cites an unknown logical leaf")
    assert old is not None
    _require(
        (old.object_id, old.content_handle) !=
        (replacement.object_id, replacement.content_handle),
        "spectral repair must introduce a new immutable leaf version",
    )
    affected = next(
        cluster
        for cluster in banked.receipt.placement
        if replacement.logical_id in cluster.member_logical_ids
    )
    untouched = tuple(
        cluster for cluster in banked.receipt.placement if cluster.cluster_id != affected.cluster_id
    )
    untouched_handles = tuple(
        banked.promotions[cluster.cluster_id].node_handle for cluster in untouched
    )
    previous[replacement.logical_id] = replacement
    updated_leaves = tuple(previous[leaf.logical_id] for leaf in banked.leaves)

    state = store.replay()
    _require(
        (state.active_assumption, state.active_fibre)
        == (banked.contract.assumption, banked.contract.fibre),
        "spectral repair cannot cross the active assumption fibre",
    )
    events: list[AtlasEvent] = []
    item = _leaf_object(replacement, banked.contract, metadata)
    existing = state.graph_objects.get(item.object_id)
    leaf_cause: tuple[str, ...] = ()
    if existing is None:
        declared = _event(
            metadata,
            EventKind.OBJECT,
            item.to_dict(),
            subject=f"leaf:{replacement.logical_id}",
            assumption=banked.contract.assumption,
            fibre=banked.contract.fibre,
        )
        events.append(declared)
        leaf_cause = (declared.event_id,)
    else:
        _require(existing == item, "repair leaf object id resolves to different content")

    node, promotion = _promote_cluster(affected, previous, banked.contract)
    promoted = promotion_event(
        promotion,
        occurred_at=metadata.occurred_at,
        producer=metadata.producer,
        actor=metadata.actor,
        correlation_id=metadata.correlation_id,
        provenance=metadata.provenance,
        runtime=metadata.runtime,
        producer_ref=metadata.producer_ref,
        goal_residual=_unknown_goal_closure(),
        causation_ids=(
            *leaf_cause,
            banked.promotion_event_ids[affected.cluster_id],
        ),
    )
    events.append(promoted)
    margin = _margin(affected.cluster_id, promoted, promotion)
    updated_promotions = dict(banked.promotions)
    updated_promotions[affected.cluster_id] = promotion
    updated_event_ids = dict(banked.promotion_event_ids)
    updated_event_ids[affected.cluster_id] = promoted.event_id
    updated_nodes = dict(banked.nodes)
    updated_nodes[affected.cluster_id] = node
    updated_margins = tuple(
        margin if old_margin.cluster_id == affected.cluster_id else old_margin
        for old_margin in banked.receipt.margins
    )
    receipt = SpectralPourReceipt.create(
        contract_handle=banked.contract.contract_handle,
        placement_operator=banked.contract.placement_operator,
        mode="repair",
        parent_pour_handle=banked.receipt.pour_handle,
        leaf_object_ids=tuple(sorted(leaf.object_id for leaf in updated_leaves)),
        placement=banked.receipt.placement,
        margins=updated_margins,
        touched_cluster_ids=(affected.cluster_id,),
        untouched_node_handles=untouched_handles,
    )
    observation = _event(
        metadata,
        EventKind.OBSERVATION,
        receipt.to_dict(),
        subject=receipt.pour_handle,
        assumption=banked.contract.assumption,
        fibre=banked.contract.fibre,
        residual=Residual(
            ResidualStatus.WITHIN_BOUND if margin.representation_sufficient
            else ResidualStatus.EXCEEDS_BOUND,
            margin.truncation_residual,
            banked.contract.phi,
            "discarded-spectral-energy-share",
            "dirty ancestor only; untouched frame handles are carried in the receipt",
        ),
        causation_ids=(
            promoted.event_id,
            banked.observation_event_id,
        ),
    )
    events.append(observation)
    store.append_many(events)
    return BankedSpectralPour(
        banked.contract,
        updated_leaves,
        receipt,
        observation.event_id,
        updated_promotions,
        updated_event_ids,
        updated_nodes,
    )


__all__ = [
    "BankedSpectralPour",
    "PourLeaf",
    "PourMetadata",
    "SpectralCluster",
    "SpectralMargin",
    "SpectralPourContract",
    "SpectralPourReceipt",
    "bank_spectral_pour",
    "derive_spectral_placement",
    "observed_pour_leaf",
    "repair_spectral_pour",
]
