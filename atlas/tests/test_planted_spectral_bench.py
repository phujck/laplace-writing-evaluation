from __future__ import annotations

import random

from atlas.bench.planted_spectral import RoutingComparison, compare_routers
from atlas.updown import ChildLeaf, UpInputs, up


def _node(cluster_id: str, vectors: list[list[float]]):
    result = up(UpInputs(
        "planted anisotropic routing",
        "planted-spectral-bench",
        "source-detail",
        "leaf",
        "cluster",
        "planted-euclidean/1",
        "axis-contract:planted-spectral/1",
        1,
        0.95,
        ("cluster", "leaf"),
        tuple(
            ChildLeaf(f"{cluster_id}:{index}", f"{cluster_id} member {index}", tuple(vector))
            for index, vector in enumerate(vectors)
        ),
    ))
    assert result.node is not None
    return result.node


def test_comparison_receipt_makes_zero_wrong_mean_frame_wins() -> None:
    receipt = RoutingComparison(200, centroid_correct=98, frame_correct=200)
    assert receipt.centroid_wrong == 102
    assert receipt.frame_wrong == 0
    assert receipt.delta == 102
    assert receipt.winner == "frame"
    assert receipt.to_dict()["direction"] == "higher-is-better"


def test_refusal_band_is_a_constructor_property_not_a_retuned_fixture() -> None:
    assert RoutingComparison(200, 100, 110).winner == "undecided"
    assert RoutingComparison(200, 100, 115).winner == "frame"
    assert RoutingComparison(200, 115, 100).winner == "centroid"


def test_frame_router_beats_centroid_on_pinned_anisotropic_plant() -> None:
    rnd = random.Random(3)
    dim = 16
    cluster_a: list[list[float]] = []
    for _ in range(12):
        vector = [0.0] * dim
        vector[0] = rnd.gauss(0.0, 10.0)
        cluster_a.append(vector)
    cluster_b: list[list[float]] = []
    for _ in range(12):
        vector = [0.0] * dim
        vector[2] = 3.0
        vector[3] = rnd.gauss(0.0, 0.4)
        cluster_b.append(vector)
    queries: list[list[float]] = []
    for _ in range(200):
        along = rnd.uniform(-14.0, 14.0)
        noise = [rnd.gauss(0.0, 0.05) for _ in range(dim)]
        noise[0] += along
        queries.append(noise)

    receipt = compare_routers(
        queries,
        ["a"] * len(queries),
        {"a": _node("a", cluster_a), "b": _node("b", cluster_b)},
    )
    assert receipt.frame_correct == 200
    assert receipt.centroid_correct < receipt.frame_correct
    assert receipt.winner == "frame"
