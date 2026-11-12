"""Planted spectral routing instruments.

The comparison receipt owns metric direction and derives its winner.  Callers never infer
whether ``0/200`` is good from prose; an inconsistent asserted winner is unrepresentable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..errors import StateTransitionRefused
from ..updown import CoarseNode


def _require(condition: bool, message: str, **fields: object) -> None:
    if not condition:
        raise StateTransitionRefused(message, **fields)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    _require(len(left) == len(right) and bool(left), "routing vectors must share a dimension")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def centroid_route_score(query: Sequence[float], node: CoarseNode) -> float:
    """The declared incumbent: cosine to the coarse centroid."""

    return _cosine(query, node.centroid)


def frame_route_score(query: Sequence[float], node: CoarseNode) -> float:
    """Score how completely the retained frame explains displacement from the centroid."""

    _require(node.frame is not None, "frame router needs a retained spectral frame")
    _require(len(query) == len(node.centroid), "query and frame centroid dimensions differ")
    displacement = [
        value - centre for value, centre in zip(query, node.centroid, strict=True)
    ]
    norm = math.sqrt(sum(value * value for value in displacement))
    _require(norm > 0.0, "frame route is undefined at the exact centroid")
    projection = [0.0] * len(displacement)
    for basis in node.frame.basis:
        _require(len(basis) == len(displacement), "frame basis dimension differs from query")
        coefficient = sum(
            value * axis for value, axis in zip(displacement, basis, strict=True)
        )
        for index, axis in enumerate(basis):
            projection[index] += coefficient * axis
    residual = math.sqrt(sum(
        (value - projected) ** 2
        for value, projected in zip(displacement, projection, strict=True)
    ))
    return max(-1.0, min(1.0, 1.0 - residual / norm))


@dataclass(frozen=True)
class RoutingComparison:
    """A direction-explicit comparison; higher correct-count is always better."""

    SCHEMA_VERSION = "atlas.planted-routing-comparison/1"
    METRIC = "correct-route-count"
    DIRECTION = "higher-is-better"

    n_probes: int
    centroid_correct: int
    frame_correct: int

    def __post_init__(self) -> None:
        _require(
            isinstance(self.n_probes, int)
            and not isinstance(self.n_probes, bool)
            and self.n_probes > 0,
            "routing comparison needs a positive probe count",
        )
        for name, value in (
            ("centroid_correct", self.centroid_correct),
            ("frame_correct", self.frame_correct),
        ):
            _require(
                isinstance(value, int)
                and not isinstance(value, bool)
                and 0 <= value <= self.n_probes,
                "routing correct count is outside the probe domain",
                field=name,
                value=value,
            )

    @property
    def centroid_wrong(self) -> int:
        return self.n_probes - self.centroid_correct

    @property
    def frame_wrong(self) -> int:
        return self.n_probes - self.frame_correct

    @property
    def delta(self) -> int:
        return self.frame_correct - self.centroid_correct

    @property
    def refusal_band(self) -> float:
        return math.sqrt(self.n_probes)

    @property
    def winner(self) -> str:
        if abs(self.delta) <= self.refusal_band:
            return "undecided"
        return "frame" if self.delta > 0 else "centroid"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "metric": self.METRIC,
            "direction": self.DIRECTION,
            "n_probes": self.n_probes,
            "centroid_correct": self.centroid_correct,
            "centroid_wrong": self.centroid_wrong,
            "frame_correct": self.frame_correct,
            "frame_wrong": self.frame_wrong,
            "delta_frame_minus_centroid": self.delta,
            "refusal_band": self.refusal_band,
            "winner": self.winner,
        }


def compare_routers(
    queries: Sequence[Sequence[float]],
    expected: Sequence[str],
    nodes: Mapping[str, CoarseNode],
) -> RoutingComparison:
    """Route the same planted probes through both operators and derive one receipt."""

    _require(len(queries) == len(expected) and bool(queries),
             "queries and planted answers must align")
    _require(len(nodes) >= 2, "routing comparison needs at least two candidates")
    ordered = tuple(sorted(nodes.items()))

    def choose(query: Sequence[float], scorer: object) -> str:
        fn = scorer  # keeps the selection below identical for both arms
        return max(
            ordered,
            key=lambda item: (fn(query, item[1]), item[0]),  # type: ignore[operator]
        )[0]

    centroid_correct = sum(
        choose(query, centroid_route_score) == answer
        for query, answer in zip(queries, expected, strict=True)
    )
    frame_correct = sum(
        choose(query, frame_route_score) == answer
        for query, answer in zip(queries, expected, strict=True)
    )
    return RoutingComparison(len(queries), centroid_correct, frame_correct)
