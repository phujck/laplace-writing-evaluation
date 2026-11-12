"""Canonical history receipts for the pure :mod:`atlas.updown` operators.

The numerical kernel deliberately owns no store.  This module is the typed seam that binds
one pure UP result to existing conceptric children and preserves the complete retained state
needed by DOWN.  Goal closure is carried by the surrounding ``AtlasEvent.residual``; the
spectral truncation residual remains a representation diagnostic inside the receipt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from .errors import SchemaFieldMissing, SchemaVersionMismatch, StateTransitionRefused
from .history import (
    AtlasEvent,
    EventKind,
    GradeAxis,
    ProducerRef,
    Residual,
    ResidualStatus,
    RuntimeReceipt,
    SeatRole,
    SourceRef,
    Validity,
)
from .ids import chash
from .updown import DownResult, UpInputs, UpResult


def _require(condition: bool, message: str, **fields: object) -> None:
    if not condition:
        raise StateTransitionRefused(message, **fields)


def _nonempty(value: str, field: str) -> None:
    _require(isinstance(value, str) and bool(value.strip()),
             "UP/DOWN history field must be non-empty", field=field)


def _finite(value: float, field: str) -> None:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool)
             and math.isfinite(float(value)),
             "UP/DOWN history number must be finite", field=field)


def _check(raw: Mapping[str, Any], schema: str, keys: tuple[str, ...], where: str) -> None:
    if raw.get("schema_version") != schema:
        raise SchemaVersionMismatch(
            f"{where} carries an unknown schema version",
            expected=schema,
            got=raw.get("schema_version"),
        )
    expected = {"schema_version", *keys}
    missing = sorted(expected - set(raw))
    extra = sorted(set(raw) - expected)
    if missing or extra:
        raise SchemaFieldMissing(
            f"{where} fields do not match its schema",
            fields=missing,
            unexpected=extra,
        )


@dataclass(frozen=True)
class UpMemberRef:
    """The stable object address and immutable content handle of one promoted child."""

    SCHEMA_VERSION = "atlas.up-member-ref/1"

    object_id: str
    content_handle: str

    def __post_init__(self) -> None:
        _nonempty(self.object_id, "object_id")
        _nonempty(self.content_handle, "content_handle")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "object_id": self.object_id,
            "content_handle": self.content_handle,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "UpMemberRef":
        _check(raw, cls.SCHEMA_VERSION, ("object_id", "content_handle"), "UpMemberRef")
        return cls(raw["object_id"], raw["content_handle"])


class GoalClosureStatus(str, Enum):
    UNMEASURED = "unmeasured"
    MEASURED = "measured"


GOAL_CLOSURE_PROBE_SET_KIND = "goal-closure-probe-set"
EXACT_MEMBER_COVERAGE = "exactly-one-probe-per-candidate-member"


def derived_cluster_id(member_logical_ids: Sequence[str]) -> str:
    """Derive the stable routing identity from exact logical leaf membership."""

    members = tuple(sorted(member_logical_ids))
    _require(
        bool(members) and all(isinstance(item, str) and item.strip() for item in members),
        "derived routing cluster requires non-empty logical member ids",
    )
    _require(
        len(members) == len(set(members)),
        "derived routing cluster logical member ids must be unique",
    )
    return "cluster:" + chash({"members": list(members)}).removeprefix("sha256:")[:20]


@dataclass(frozen=True)
class GoalClosureProbe:
    """One banked retrieval question and its independently fixed expected answer."""

    SCHEMA_VERSION = "atlas.goal-closure-probe/1"

    probe_id: str
    question: str
    query_vector: tuple[float, ...]
    expected_leaf_id: str
    expected_source_chain: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("probe_id", "question", "expected_leaf_id"):
            _nonempty(str(getattr(self, field_name)), field_name)
        _require(bool(self.query_vector), "goal closure probe query must be non-empty")
        for value in self.query_vector:
            _finite(value, "query_vector")
        _require(
            bool(self.expected_source_chain) and all(self.expected_source_chain),
            "goal closure probe must name a complete expected source chain",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "probe_id": self.probe_id,
            "question": self.question,
            "query_vector": list(self.query_vector),
            "expected_leaf_id": self.expected_leaf_id,
            "expected_source_chain": list(self.expected_source_chain),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GoalClosureProbe":
        _check(
            raw,
            cls.SCHEMA_VERSION,
            (
                "probe_id",
                "question",
                "query_vector",
                "expected_leaf_id",
                "expected_source_chain",
            ),
            "GoalClosureProbe",
        )
        return cls(
            raw["probe_id"],
            raw["question"],
            tuple(raw["query_vector"]),
            raw["expected_leaf_id"],
            tuple(raw["expected_source_chain"]),
        )


@dataclass(frozen=True)
class GoalClosureProbeSet:
    """The resolvable, content-addressed exam behind a measured closure claim."""

    SCHEMA_VERSION = "atlas.goal-closure-probe-set/2"

    assumption: str
    fibre: str
    coverage_contract: str
    probes: tuple[GoalClosureProbe, ...]

    def __post_init__(self) -> None:
        _nonempty(self.assumption, "probe_set.assumption")
        _nonempty(self.fibre, "probe_set.fibre")
        _require(
            self.coverage_contract == EXACT_MEMBER_COVERAGE,
            "goal closure probe set must name the exact candidate-member coverage contract",
        )
        _require(bool(self.probes), "measured goal closure cannot bank an empty exam")
        probe_ids = [probe.probe_id for probe in self.probes]
        _require(
            len(probe_ids) == len(set(probe_ids)),
            "goal closure probe ids must be unique",
        )

    @property
    def handle(self) -> str:
        return chash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "assumption": self.assumption,
            "fibre": self.fibre,
            "coverage_contract": self.coverage_contract,
            "probes": [probe.to_dict() for probe in self.probes],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GoalClosureProbeSet":
        _check(
            raw,
            cls.SCHEMA_VERSION,
            ("assumption", "fibre", "coverage_contract", "probes"),
            "GoalClosureProbeSet",
        )
        return cls(
            raw["assumption"],
            raw["fibre"],
            raw["coverage_contract"],
            tuple(GoalClosureProbe.from_dict(item) for item in raw["probes"]),
        )


@dataclass(frozen=True)
class GoalClosureAnswer:
    """One observed answer; truth booleans must agree with its banked probe definition."""

    SCHEMA_VERSION = "atlas.goal-closure-answer/1"

    probe_id: str
    selected_leaf_id: str
    source_chain: tuple[str, ...]
    correct_leaf: bool
    complete_source_chain: bool
    passed: bool

    def __post_init__(self) -> None:
        _nonempty(self.probe_id, "answer.probe_id")
        _nonempty(self.selected_leaf_id, "answer.selected_leaf_id")
        _require(bool(self.source_chain), "goal closure answer source chain must be non-empty")
        for field_name in ("correct_leaf", "complete_source_chain", "passed"):
            _require(
                isinstance(getattr(self, field_name), bool),
                "goal closure answer truth fields must be boolean",
                field=field_name,
            )
        _require(
            self.passed == (self.correct_leaf and self.complete_source_chain),
            "goal closure answer pass flag contradicts its component checks",
            probe_id=self.probe_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "probe_id": self.probe_id,
            "selected_leaf_id": self.selected_leaf_id,
            "source_chain": list(self.source_chain),
            "correct_leaf": self.correct_leaf,
            "complete_source_chain": self.complete_source_chain,
            "passed": self.passed,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GoalClosureAnswer":
        _check(
            raw,
            cls.SCHEMA_VERSION,
            (
                "probe_id",
                "selected_leaf_id",
                "source_chain",
                "correct_leaf",
                "complete_source_chain",
                "passed",
            ),
            "GoalClosureAnswer",
        )
        return cls(
            raw["probe_id"],
            raw["selected_leaf_id"],
            tuple(raw["source_chain"]),
            raw["correct_leaf"],
            raw["complete_source_chain"],
            raw["passed"],
        )


@dataclass(frozen=True)
class GoalClosureRoutingCandidate:
    """A coarse routing candidate with exact resolved members and derived centroid."""

    SCHEMA_VERSION = "atlas.goal-closure-routing-candidate/1"

    cluster_id: str
    node_handle: str
    centroid: tuple[float, ...]
    members: tuple[UpMemberRef, ...]

    def __post_init__(self) -> None:
        _nonempty(self.cluster_id, "routing_candidate.cluster_id")
        _nonempty(self.node_handle, "routing_candidate.node_handle")
        _require(bool(self.centroid), "routing candidate centroid must be non-empty")
        for value in self.centroid:
            _finite(value, "routing_candidate.centroid")
        _require(bool(self.members), "routing candidate must name exact members")
        object_ids = [member.object_id for member in self.members]
        _require(
            len(object_ids) == len(set(object_ids)),
            "routing candidate member objects must be unique",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "cluster_id": self.cluster_id,
            "node_handle": self.node_handle,
            "centroid": list(self.centroid),
            "members": [member.to_dict() for member in self.members],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GoalClosureRoutingCandidate":
        _check(
            raw,
            cls.SCHEMA_VERSION,
            ("cluster_id", "node_handle", "centroid", "members"),
            "GoalClosureRoutingCandidate",
        )
        return cls(
            raw["cluster_id"],
            raw["node_handle"],
            tuple(raw["centroid"]),
            tuple(UpMemberRef.from_dict(item) for item in raw["members"]),
        )


@dataclass(frozen=True)
class GoalClosureObservation:
    """A preview-grade exam result bound exactly by a later UP receipt."""

    SCHEMA_VERSION = "atlas.goal-closure-observation/2"

    probe_set_handle: str
    promoted_handles: tuple[str, ...]
    candidates: tuple[GoalClosureRoutingCandidate, ...]
    answers: tuple[GoalClosureAnswer, ...]
    phase: str = "preview"

    def __post_init__(self) -> None:
        _nonempty(self.probe_set_handle, "observation.probe_set_handle")
        _require(self.phase == "preview", "goal closure observation phase must be preview")
        _require(
            bool(self.promoted_handles) and all(self.promoted_handles),
            "goal closure observation must name at least one evaluated promotion",
        )
        candidate_handles = [candidate.node_handle for candidate in self.candidates]
        candidate_ids = [candidate.cluster_id for candidate in self.candidates]
        _require(
            bool(candidate_handles) and len(candidate_handles) == len(set(candidate_handles)),
            "goal closure routing candidates must be non-empty and unique",
        )
        _require(
            len(candidate_ids) == len(set(candidate_ids)),
            "goal closure routing candidate identities must be unique",
        )
        _require(
            set(candidate_handles) == set(self.promoted_handles),
            "promoted handles must equal the exact routing candidate handles",
        )
        _require(bool(self.answers), "measured goal closure cannot cite an empty answer list")
        answer_ids = [answer.probe_id for answer in self.answers]
        _require(
            len(answer_ids) == len(set(answer_ids)),
            "goal closure observation answer ids must be unique",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "phase": self.phase,
            "probe_set_handle": self.probe_set_handle,
            "promoted_handles": list(self.promoted_handles),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "answers": [answer.to_dict() for answer in self.answers],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GoalClosureObservation":
        _check(
            raw,
            cls.SCHEMA_VERSION,
            ("phase", "probe_set_handle", "promoted_handles", "candidates", "answers"),
            "GoalClosureObservation",
        )
        return cls(
            raw["probe_set_handle"],
            tuple(raw["promoted_handles"]),
            tuple(
                GoalClosureRoutingCandidate.from_dict(item)
                for item in raw["candidates"]
            ),
            tuple(GoalClosureAnswer.from_dict(item) for item in raw["answers"]),
            raw["phase"],
        )


@dataclass(frozen=True)
class GoalClosureClaim:
    """Typed closure posture; measured claims must name their probe evidence."""

    SCHEMA_VERSION = "atlas.goal-closure-claim/2"

    status: GoalClosureStatus
    probe_set_handle: str | None
    probe_event_id: str | None
    observation_handle: str | None
    note: str

    def __post_init__(self) -> None:
        _require(isinstance(self.status, GoalClosureStatus),
                 "goal closure status must be typed")
        _nonempty(self.note, "goal_closure.note")
        if self.status == GoalClosureStatus.UNMEASURED:
            _require(
                self.probe_set_handle is None
                and self.probe_event_id is None
                and self.observation_handle is None,
                     "unmeasured goal closure cannot cite measured probe evidence")
        else:
            _nonempty(str(self.probe_set_handle or ""), "probe_set_handle")
            _nonempty(str(self.probe_event_id or ""), "probe_event_id")
            _nonempty(str(self.observation_handle or ""), "observation_handle")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "status": self.status.value,
            "probe_set_handle": self.probe_set_handle,
            "probe_event_id": self.probe_event_id,
            "observation_handle": self.observation_handle,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GoalClosureClaim":
        _check(
            raw,
            cls.SCHEMA_VERSION,
            (
                "status", "probe_set_handle", "probe_event_id",
                "observation_handle", "note",
            ),
            "GoalClosureClaim",
        )
        return cls(
            GoalClosureStatus(raw["status"]),
            raw["probe_set_handle"],
            raw["probe_event_id"],
            raw["observation_handle"],
            raw["note"],
        )


@dataclass(frozen=True)
class RetainedFrameReceipt:
    """The full member-aligned spectral state from which prolongation operates."""

    SCHEMA_VERSION = "atlas.retained-frame/1"

    basis: tuple[tuple[float, ...], ...]
    weights: tuple[float, ...]
    coordinates: tuple[tuple[float, ...], ...]
    chi_declared: int
    chi_kept: int
    truncation_residual: float
    degenerate_cut: bool

    def __post_init__(self) -> None:
        _require(isinstance(self.chi_declared, int) and not isinstance(self.chi_declared, bool)
                 and self.chi_declared >= 1, "declared chi must be positive")
        _require(isinstance(self.chi_kept, int) and not isinstance(self.chi_kept, bool)
                 and 0 <= self.chi_kept <= self.chi_declared,
                 "kept chi contradicts declared chi")
        _require(len(self.basis) == len(self.weights) == self.chi_kept,
                 "retained basis, weights and kept chi must align")
        for value in self.weights:
            _finite(value, "weight")
            _require(value >= 0.0, "retained spectral weights cannot be negative")
        basis_widths = {len(row) for row in self.basis}
        _require(len(basis_widths) <= 1,
                 "retained basis rows must share one vector dimension")
        for row in self.basis:
            _require(bool(row), "retained basis vectors must be non-empty")
            for value in row:
                _finite(value, "frame value")
        for row in self.coordinates:
            _require(len(row) == self.chi_kept,
                     "member coordinates must align with retained rank")
            for value in row:
                _finite(value, "frame value")
        _finite(self.truncation_residual, "truncation_residual")
        _require(0.0 <= self.truncation_residual <= 1.0,
                 "truncation residual must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "basis": [list(row) for row in self.basis],
            "weights": list(self.weights),
            "coordinates": [list(row) for row in self.coordinates],
            "chi_declared": self.chi_declared,
            "chi_kept": self.chi_kept,
            "truncation_residual": self.truncation_residual,
            "degenerate_cut": self.degenerate_cut,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RetainedFrameReceipt":
        keys = (
            "basis", "weights", "coordinates", "chi_declared", "chi_kept",
            "truncation_residual", "degenerate_cut",
        )
        _check(raw, cls.SCHEMA_VERSION, keys, "RetainedFrameReceipt")
        return cls(
            tuple(tuple(row) for row in raw["basis"]),
            tuple(raw["weights"]),
            tuple(tuple(row) for row in raw["coordinates"]),
            raw["chi_declared"],
            raw["chi_kept"],
            raw["truncation_residual"],
            raw["degenerate_cut"],
        )


@dataclass(frozen=True)
class UpActReceipt:
    """One atomic promotion: both faces and exact descent handles from the same members."""

    SCHEMA_VERSION = "atlas.up-history-act/2"

    act_handle: str
    inputs_handle: str
    node_handle: str
    assumption: str
    fibre: str
    grade_axis: GradeAxis
    coarse_to_fine: tuple[str | int, ...]
    metric_version: str
    chi: int
    phi: float
    members: tuple[UpMemberRef, ...]
    semantic_face: str
    semantic_sources: tuple[str, ...]
    frame: RetainedFrameReceipt
    centroid: tuple[float, ...]
    representation_sufficient: bool
    forced_descent: str | None
    goal_closure: GoalClosureClaim

    def __post_init__(self) -> None:
        for field in (
            "act_handle", "inputs_handle", "node_handle", "assumption", "fibre",
            "metric_version", "semantic_face",
        ):
            _nonempty(getattr(self, field), field)
        _require(isinstance(self.goal_closure, GoalClosureClaim),
                 "goal closure must be a typed claim")
        _require(self.grade_axis.from_coordinate != self.grade_axis.to_coordinate,
                 "UP receipt must change grade")
        _require(len(self.coarse_to_fine) >= 2
                 and len(set(self.coarse_to_fine)) == len(self.coarse_to_fine),
                 "UP receipt must bind a distinct coarse-to-fine order")
        _require(self.grade_axis.from_coordinate in self.coarse_to_fine
                 and self.grade_axis.to_coordinate in self.coarse_to_fine,
                 "UP receipt grades are absent from its declared order")
        _require(self.coarse_to_fine.index(self.grade_axis.from_coordinate)
                 > self.coarse_to_fine.index(self.grade_axis.to_coordinate),
                 "UP receipt direction is not coarseward")
        _require(self.chi == self.frame.chi_declared,
                 "UP receipt chi contradicts retained frame")
        _finite(self.phi, "phi")
        _require(0.0 < self.phi <= 1.0, "phi must be in (0, 1]")
        _require(bool(self.members) and len({m.object_id for m in self.members}) == len(self.members)
                 and len({m.content_handle for m in self.members}) == len(self.members),
                 "UP members must be non-empty and unique")
        _require(len(self.frame.coordinates) == len(self.members),
                 "retained coordinates must align with UP membership")
        handles = {member.content_handle for member in self.members}
        _require(set(self.semantic_sources) <= handles,
                 "semantic sources must resolve within UP membership")
        for value in self.centroid:
            _finite(value, "centroid")
        _require(bool(self.centroid), "UP centroid must be non-empty")
        _require(all(len(row) == len(self.centroid) for row in self.frame.basis),
                 "retained basis dimension must match the centroid")
        _require(
            self.act_handle
            == chash({"up": self.inputs_handle, "node": self.node_handle}),
            "UP act handle does not verify against its inputs and node",
        )
        expected_sufficient = (
            self.frame.truncation_residual <= self.phi and not self.frame.degenerate_cut
        )
        _require(self.representation_sufficient == expected_sufficient,
                 "UP representation sufficiency contradicts its retained frame and phi")
        if self.representation_sufficient:
            _require(self.forced_descent is None,
                     "sufficient representation cannot force descent")
        else:
            _nonempty(str(self.forced_descent or ""), "forced_descent")

    @property
    def coarse_object_id(self) -> str:
        return "coarse:" + self.node_handle.removeprefix("sha256:")

    @property
    def semantic_object_id(self) -> str:
        return "semantic:" + chash({
            "node": self.node_handle,
            "face": self.semantic_face,
            "sources": list(self.semantic_sources),
        }).removeprefix("sha256:")

    @property
    def spectral_object_id(self) -> str:
        return "spectral:" + chash({
            "node": self.node_handle,
            "frame": self.frame.to_dict(),
            "centroid": list(self.centroid),
        }).removeprefix("sha256:")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "act_handle": self.act_handle,
            "inputs_handle": self.inputs_handle,
            "node_handle": self.node_handle,
            "assumption": self.assumption,
            "fibre": self.fibre,
            "grade_axis": self.grade_axis.to_dict(),
            "coarse_to_fine": list(self.coarse_to_fine),
            "metric_version": self.metric_version,
            "chi": self.chi,
            "phi": self.phi,
            "members": [member.to_dict() for member in self.members],
            "semantic_face": self.semantic_face,
            "semantic_sources": list(self.semantic_sources),
            "frame": self.frame.to_dict(),
            "centroid": list(self.centroid),
            "representation_sufficient": self.representation_sufficient,
            "forced_descent": self.forced_descent,
            "goal_closure": self.goal_closure.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "UpActReceipt":
        keys = (
            "act_handle", "inputs_handle", "node_handle", "assumption", "fibre",
            "grade_axis", "coarse_to_fine", "metric_version", "chi", "phi", "members",
            "semantic_face", "semantic_sources", "frame", "centroid",
            "representation_sufficient", "forced_descent", "goal_closure",
        )
        _check(raw, cls.SCHEMA_VERSION, keys, "UpActReceipt")
        return cls(
            raw["act_handle"], raw["inputs_handle"], raw["node_handle"],
            raw["assumption"], raw["fibre"], GradeAxis.from_dict(raw["grade_axis"]),
            tuple(raw["coarse_to_fine"]), raw["metric_version"], raw["chi"], raw["phi"],
            tuple(UpMemberRef.from_dict(item) for item in raw["members"]),
            raw["semantic_face"], tuple(raw["semantic_sources"]),
            RetainedFrameReceipt.from_dict(raw["frame"]), tuple(raw["centroid"]),
            raw["representation_sufficient"], raw["forced_descent"],
            GoalClosureClaim.from_dict(raw["goal_closure"]),
        )


@dataclass(frozen=True)
class DownActReceipt:
    """A prolongation causally bound to one already-banked promotion."""

    SCHEMA_VERSION = "atlas.down-history-act/1"

    act_handle: str
    up_event_id: str
    up_act_handle: str
    node_handle: str
    coarse_object_id: str
    members: tuple[UpMemberRef, ...]
    reconstructions: Mapping[str, tuple[float, ...]]
    verified: bool
    round_trip_residual: float | None

    def __post_init__(self) -> None:
        for field in (
            "act_handle", "up_event_id", "up_act_handle", "node_handle", "coarse_object_id",
        ):
            _nonempty(getattr(self, field), field)
        handles = tuple(member.content_handle for member in self.members)
        _require(bool(handles) and set(self.reconstructions) == set(handles),
                 "DOWN reconstructions must resolve every promoted member exactly")
        _require(
            self.act_handle
            == chash({
                "down": self.node_handle,
                "members": list(handles),
                "verified": self.verified,
            }),
            "DOWN act handle does not verify against its node, members and verification state",
        )
        for vector in self.reconstructions.values():
            _require(bool(vector), "DOWN reconstruction vector must be non-empty")
            for value in vector:
                _finite(value, "reconstruction")
        _require(self.verified == (self.round_trip_residual is not None),
                 "DOWN verification and measured residual contradict")
        if self.round_trip_residual is not None:
            _finite(self.round_trip_residual, "round_trip_residual")
            _require(self.round_trip_residual >= 0.0,
                     "round-trip residual cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "act_handle": self.act_handle,
            "up_event_id": self.up_event_id,
            "up_act_handle": self.up_act_handle,
            "node_handle": self.node_handle,
            "coarse_object_id": self.coarse_object_id,
            "members": [member.to_dict() for member in self.members],
            "reconstructions": {
                handle: list(vector) for handle, vector in sorted(self.reconstructions.items())
            },
            "verified": self.verified,
            "round_trip_residual": self.round_trip_residual,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "DownActReceipt":
        keys = (
            "act_handle", "up_event_id", "up_act_handle", "node_handle",
            "coarse_object_id", "members", "reconstructions", "verified",
            "round_trip_residual",
        )
        _check(raw, cls.SCHEMA_VERSION, keys, "DownActReceipt")
        return cls(
            raw["act_handle"], raw["up_event_id"], raw["up_act_handle"],
            raw["node_handle"], raw["coarse_object_id"],
            tuple(UpMemberRef.from_dict(item) for item in raw["members"]),
            {handle: tuple(vector) for handle, vector in raw["reconstructions"].items()},
            raw["verified"], raw["round_trip_residual"],
        )


def bind_up_result(
    inputs: UpInputs,
    result: UpResult,
    member_object_ids: Mapping[str, str],
) -> UpActReceipt:
    """Bind a pure UP result to exact existing object ids, without touching the store."""

    _require(result.node is not None and result.node.frame is not None,
             "UP result has no retained coarse node")
    node = result.node
    expected = tuple(child.handle for child in inputs.children)
    _require(node.member_handles == expected,
             "UP result membership contradicts its inputs")
    _require(set(member_object_ids) == set(expected),
             "member object map must resolve every child handle exactly")
    frame = RetainedFrameReceipt(
        node.frame.basis, node.frame.weights, node.frame.coordinates,
        node.frame.chi_declared, node.frame.chi_kept,
        node.frame.truncation_residual, node.frame.degenerate_cut,
    )
    return UpActReceipt(
        result.act_handle, result.inputs_handle, node.node_handle,
        inputs.assumption, inputs.fibre,
        GradeAxis(inputs.grade_contract_id, inputs.axis, inputs.from_grade, inputs.to_grade),
        inputs.coarse_to_fine, inputs.metric_version, inputs.chi, inputs.phi,
        tuple(UpMemberRef(member_object_ids[handle], handle) for handle in expected),
        node.semantic_face, node.semantic_sources, frame, node.centroid,
        result.representation_sufficient,
        result.forced_descent,
        GoalClosureClaim(
            GoalClosureStatus.UNMEASURED,
            None,
            None,
            None,
            result.goal_closure,
        ),
    )


def bind_down_result(
    up_event_id: str,
    promotion: UpActReceipt,
    result: DownResult,
) -> DownActReceipt:
    """Bind DOWN to the exact promotion event and members it prolongs."""

    _require(result.node_handle == promotion.node_handle,
             "DOWN result cites a different coarse node")
    expected = tuple(member.content_handle for member in promotion.members)
    _require(result.child_handles == expected,
             "DOWN result membership contradicts its promotion")
    return DownActReceipt(
        result.act_handle, up_event_id, promotion.act_handle, promotion.node_handle,
        promotion.coarse_object_id, promotion.members,
        {handle: tuple(vector) for handle, vector in result.reconstructions.items()},
        result.verified, result.round_trip_residual,
    )


def promotion_event(
    receipt: UpActReceipt,
    *,
    occurred_at: str,
    producer: SeatRole,
    actor: SeatRole,
    correlation_id: str,
    provenance: tuple[SourceRef, ...],
    runtime: RuntimeReceipt,
    producer_ref: ProducerRef,
    goal_residual: Residual,
    causation_ids: tuple[str, ...] = (),
    validity: Validity = Validity.VALID,
) -> AtlasEvent:
    """Create the one canonical event whose residual is goal closure, never truncation."""

    _require(goal_residual.unit == "goal-closure",
             "promotion event residual must measure goal closure")
    if receipt.goal_closure.status == GoalClosureStatus.UNMEASURED:
        _require(goal_residual.status == ResidualStatus.UNKNOWN,
                 "unmeasured pure UP cannot claim measured goal closure")
    else:
        _require(goal_residual.status != ResidualStatus.UNKNOWN,
                 "measured goal closure cannot carry an unknown residual")
        assert receipt.goal_closure.probe_event_id is not None
        assert receipt.goal_closure.probe_set_handle is not None
        _require(receipt.goal_closure.probe_event_id in causation_ids,
                 "measured goal closure must causally cite its probe observation")
        _require(any(
            source.digest == receipt.goal_closure.probe_set_handle
            for source in provenance
        ), "measured goal closure must carry its probe-set handle in provenance")
    return AtlasEvent.create(
        occurred_at=occurred_at, kind=EventKind.PROMOTION, producer=producer, actor=actor,
        subject=receipt.act_handle, assumption=receipt.assumption, fibre=receipt.fibre,
        correlation_id=correlation_id, causation_ids=causation_ids, provenance=provenance,
        residual=goal_residual, runtime=runtime, producer_ref=producer_ref,
        validity=validity, payload=receipt.to_dict(),
    )


def prolongation_event(
    receipt: DownActReceipt,
    promotion: UpActReceipt,
    *,
    occurred_at: str,
    producer: SeatRole,
    actor: SeatRole,
    correlation_id: str,
    provenance: tuple[SourceRef, ...],
    runtime: RuntimeReceipt,
    producer_ref: ProducerRef,
    residual: Residual,
    validity: Validity = Validity.VALID,
) -> AtlasEvent:
    """Create a DOWN event with the promotion event as its mandatory causal parent."""

    _require(receipt.up_act_handle == promotion.act_handle
             and receipt.node_handle == promotion.node_handle
             and receipt.members == promotion.members,
             "DOWN event receipt contradicts its UP receipt")
    if receipt.verified:
        _require(residual.unit == "round-trip-relative-error",
                 "verified DOWN residual must use the round-trip relative-error unit")
        _require(residual.status != ResidualStatus.UNKNOWN
                 and residual.value == receipt.round_trip_residual,
                 "verified DOWN event must carry its measured round-trip residual")
    else:
        _require(residual.unit == "round-trip-relative-error",
                 "unverified DOWN residual must name the unmeasured round-trip unit")
        _require(residual.status == ResidualStatus.UNKNOWN,
                 "unverified DOWN event residual must remain unknown")
    return AtlasEvent.create(
        occurred_at=occurred_at, kind=EventKind.PROLONGATION, producer=producer, actor=actor,
        subject=receipt.act_handle, assumption=promotion.assumption,
        fibre=promotion.fibre,
        correlation_id=correlation_id, causation_ids=(receipt.up_event_id,),
        provenance=provenance, residual=residual, runtime=runtime,
        producer_ref=producer_ref, validity=validity, payload=receipt.to_dict(),
    )
