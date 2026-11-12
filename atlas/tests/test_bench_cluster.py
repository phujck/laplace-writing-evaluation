"""test_bench_cluster.py - the numpy spectral clusterer: deterministic, correct, and honest.

The clusterer decides the SHAPE of both Phase 3 trees, so a defect here is a defect in two arms
at once and would be invisible in their correctness numbers. Four things are pinned:

  * it RECOVERS known structure - three separated directions come back as three clusters;
  * it is DETERMINISTIC at a seed, including the sampled path that large inputs take;
  * the branch band narrows WHICH K is chosen without changing HOW, and the unconstrained choice
    is still reported - the number RAPTOR's fold record uses to state its own compromise;
  * degenerate geometry (identical points) scores 0 rather than NaN. That one is not cosmetic:
    a NaN silhouette propagates through the max and silently decides K.
"""

from __future__ import annotations

import numpy as np

from atlas.bench.cluster import BRANCH_MAX, Split, _silhouette, best_split


def _blobs(centers: int = 3, per: int = 60, dim: int = 16, spread: float = 0.25,
           seed: int = 0) -> np.ndarray:
    """Well-separated unit-norm directions. Normalized AFTER offsetting, as real vectors are."""
    rng = np.random.default_rng(seed)
    basis = np.eye(centers, dim) * 5.0
    X = np.vstack([rng.normal(0.0, spread, (per, dim)) + basis[i] for i in range(centers)])
    return (X / np.linalg.norm(X, axis=1, keepdims=True)).astype(np.float32)


def test_it_recovers_three_separated_clusters():
    X = _blobs(centers=3, per=60)
    split = best_split(X, seed=7)
    assert split.k == 3
    assert split.silhouette > 0.8
    sizes = sorted(int((split.labels == j).sum()) for j in range(split.k))
    assert sizes == [60, 60, 60]


def test_the_recovered_labels_agree_with_the_planted_truth():
    X = _blobs(centers=3, per=40)
    labels = best_split(X, seed=7).labels
    truth = np.repeat(np.arange(3), 40)
    # A clustering is only defined up to a relabelling, so purity is the property to assert.
    for j in np.unique(labels):
        assert len(set(truth[labels == j])) == 1


def test_it_is_deterministic_at_a_seed():
    X = _blobs()
    a, b = best_split(X, seed=7), best_split(X, seed=7)
    assert a.k == b.k
    assert np.array_equal(a.labels, b.labels)
    assert a.silhouette == b.silhouette


def test_the_sampled_path_is_also_deterministic():
    """Above the sample cap a split runs on a seeded sample and extends out of sample."""
    X = _blobs(centers=4, per=80)
    a = best_split(X, seed=3, sample_cap=100)
    b = best_split(X, seed=3, sample_cap=100)
    assert a.sampled == 100 and a.total == len(X)
    assert np.array_equal(a.labels, b.labels)
    assert len(a.labels) == len(X), "every member is labelled, sampled or not"


def test_the_branch_band_moves_the_choice_and_records_what_it_overrode():
    X = _blobs(centers=2, per=80)
    free = best_split(X, seed=5)
    banded = best_split(X, seed=5, branch_min=6)
    assert free.k == 2, "unconstrained silhouette prefers the coarse split on 2 blobs"
    assert banded.k >= 6, "the band's floor binds"
    assert banded.unconstrained_k == free.k, "the override is recorded, not hidden"
    assert banded.silhouette <= free.silhouette, "the band costs cluster quality, and says so"


def test_the_band_never_exceeds_the_engines_branch_max():
    X = _blobs(centers=3, per=100)
    assert best_split(X, seed=5, branch_min=6).k <= BRANCH_MAX


def test_a_tiny_input_refuses_to_split_rather_than_inventing_clusters():
    X = _blobs(centers=1, per=3)
    split = best_split(X, seed=1)
    assert split.k == 1
    assert set(split.labels.tolist()) == {0}


def test_identical_points_score_zero_silhouette_not_nan():
    dist = np.zeros((6, 6))
    labels = np.array([0, 0, 0, 1, 1, 1])
    value = _silhouette(dist, labels)
    assert value == 0.0
    assert not np.isnan(value)


def test_a_single_cluster_labelling_scores_the_sentinel():
    dist = np.ones((4, 4)) - np.eye(4)
    assert _silhouette(dist, np.zeros(4, dtype=int)) == -1.0


def test_the_split_record_carries_its_own_provenance():
    X = _blobs(centers=3, per=50)
    split = best_split(X, seed=2)
    assert isinstance(split, Split)
    assert split.total == len(X)
    assert 0 < split.sampled <= len(X)
