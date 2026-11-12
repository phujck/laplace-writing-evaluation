from __future__ import annotations

import pytest

from atlas.errors import StateTransitionRefused
from atlas.routing import RawCosineRouter, RouteCandidate, RoutingContext


def context(grade: str = "leaf") -> RoutingContext:
    return RoutingContext(
        "assumption",
        "fibre",
        grade,
        "axis-contract:test/1",
        "semantic-test-lens/1",
        "encoder:test/1",
    )


def test_raw_cosine_router_is_direction_typed_and_context_receipted() -> None:
    router = RawCosineRouter()
    ranked = router.rank(
        (1.0, 0.0),
        (
            RouteCandidate("wrong", (0.0, 1.0)),
            RouteCandidate("right", (1.0, 0.0)),
        ),
        context(),
    )

    assert [item.candidate_id for item in ranked] == ["right", "wrong"]
    assert router.receipt(context("cluster")).to_dict() == {
        "operator_version": "raw-cosine-router/1",
        "metric_version": "cosine-similarity/1",
        "direction": "higher-is-better",
        "proof_jurisdiction": "bootstrap-crutch",
        "assumption": "assumption",
        "fibre": "fibre",
        "grade": "cluster",
        "grade_axis_contract_id": "axis-contract:test/1",
        "lens_id": "semantic-test-lens/1",
        "encoder_spec_id": "encoder:test/1",
    }


def test_raw_cosine_router_refuses_dimension_contradiction() -> None:
    with pytest.raises(StateTransitionRefused, match="dimensions contradict"):
        RawCosineRouter().rank(
            (1.0, 0.0),
            (RouteCandidate("candidate", (1.0, 0.0, 0.0)),),
            context(),
        )
