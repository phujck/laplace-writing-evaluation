"""Typed, replaceable routing operators.

Candidate generation and ranking are evidence-producing acts, never authority judgements.  The
first implementation is deliberately the raw-cosine crutch; its interface and receipts make a
fibred, graded diffusion operator replaceable without changing reconstruction semantics.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

from .errors import StateTransitionRefused


def _nonempty(value: str, name: str) -> None:
    if not value.strip():
        raise StateTransitionRefused(f"routing {name} is empty")


@dataclass(frozen=True)
class RoutingContext:
    assumption: str
    fibre: str
    grade: str
    grade_axis_contract_id: str
    lens_id: str
    encoder_spec_id: str

    def __post_init__(self) -> None:
        for name, value in (
            ("assumption", self.assumption),
            ("fibre", self.fibre),
            ("grade", self.grade),
            ("grade_axis_contract_id", self.grade_axis_contract_id),
            ("lens_id", self.lens_id),
            ("encoder_spec_id", self.encoder_spec_id),
        ):
            _nonempty(value, name)

    def to_dict(self) -> dict[str, str]:
        return {
            "assumption": self.assumption,
            "fibre": self.fibre,
            "grade": self.grade,
            "grade_axis_contract_id": self.grade_axis_contract_id,
            "lens_id": self.lens_id,
            "encoder_spec_id": self.encoder_spec_id,
        }


@dataclass(frozen=True)
class RouteCandidate:
    candidate_id: str
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        _nonempty(self.candidate_id, "candidate id")
        if not self.vector or not all(math.isfinite(value) for value in self.vector):
            raise StateTransitionRefused("routing candidate vector is empty or non-finite")


@dataclass(frozen=True)
class RouteScore:
    candidate_id: str
    score: float


@dataclass(frozen=True)
class RoutingOperatorReceipt:
    operator_version: str
    metric_version: str
    direction: str
    proof_jurisdiction: str
    context: RoutingContext

    def to_dict(self) -> dict[str, object]:
        return {
            "operator_version": self.operator_version,
            "metric_version": self.metric_version,
            "direction": self.direction,
            "proof_jurisdiction": self.proof_jurisdiction,
            **self.context.to_dict(),
        }


class RoutingOperator(Protocol):
    operator_version: str
    metric_version: str
    direction: str
    proof_jurisdiction: str

    def rank(
        self,
        query: Sequence[float],
        candidates: Sequence[RouteCandidate],
        context: RoutingContext,
    ) -> tuple[RouteScore, ...]: ...

    def receipt(self, context: RoutingContext) -> RoutingOperatorReceipt: ...


@dataclass(frozen=True)
class RawCosineRouter:
    """The explicit bootstrap crutch, isolated behind the production operator boundary."""

    operator_version: str = "raw-cosine-router/1"
    metric_version: str = "cosine-similarity/1"
    direction: str = "higher-is-better"
    proof_jurisdiction: str = "bootstrap-crutch"

    def __post_init__(self) -> None:
        for name, value in (
            ("operator_version", self.operator_version),
            ("metric_version", self.metric_version),
            ("direction", self.direction),
            ("proof_jurisdiction", self.proof_jurisdiction),
        ):
            _nonempty(value, name)
        if self.direction != "higher-is-better":
            raise StateTransitionRefused("raw cosine router direction must be higher-is-better")

    def receipt(self, context: RoutingContext) -> RoutingOperatorReceipt:
        return RoutingOperatorReceipt(
            self.operator_version,
            self.metric_version,
            self.direction,
            self.proof_jurisdiction,
            context,
        )

    def rank(
        self,
        query: Sequence[float],
        candidates: Sequence[RouteCandidate],
        context: RoutingContext,
    ) -> tuple[RouteScore, ...]:
        del context  # identity is still carried in the receipt; raw cosine has no local state.
        if not query or not all(math.isfinite(value) for value in query):
            raise StateTransitionRefused("routing query vector is empty or non-finite")
        query_norm = math.sqrt(sum(value * value for value in query)) or 1.0
        scored: list[RouteScore] = []
        for candidate in candidates:
            if len(candidate.vector) != len(query):
                raise StateTransitionRefused(
                    "routing vector dimensions contradict",
                    query_dimensions=len(query),
                    candidate_dimensions=len(candidate.vector),
                    candidate_id=candidate.candidate_id,
                )
            candidate_norm = math.sqrt(
                sum(value * value for value in candidate.vector)
            ) or 1.0
            score = sum(
                left * right for left, right in zip(query, candidate.vector, strict=True)
            ) / (query_norm * candidate_norm)
            scored.append(RouteScore(candidate.candidate_id, score))
        scored.sort(key=lambda item: (-item.score, item.candidate_id))
        return tuple(scored)


__all__ = [
    "RawCosineRouter",
    "RouteCandidate",
    "RouteScore",
    "RoutingContext",
    "RoutingOperator",
    "RoutingOperatorReceipt",
]
