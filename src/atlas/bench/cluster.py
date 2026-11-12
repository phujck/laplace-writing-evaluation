"""cluster.py - silhouette-chosen-K spectral splitting, ported as an IDEA and written in numpy.

THE PORT, and what "atlas-clean" means here. The engine picks its concept-tree structure with a
silhouette sweep over spectral clusterings of a cosine affinity (``src/laplace/meaning_upfold.py``
``_best_split``): build ``A = (XX' + 1)/2``, spectral-cluster it for each K in ``[2, 8]``, score
each clustering by silhouette on the cosine distance, keep the best K. The atlas cannot import
that function - the seal forbids it, and a copied import would be the seal dissolving by accretion
(seam J8). So the METHOD is reproduced here from its description and the arithmetic is written
against numpy.

WHY NOT sklearn, which is installed and which the engine uses. The atlas runtime is numpy and
nothing else (``atlas/pyproject.toml`` declares exactly one dependency, and says why). Spectral
clustering is an affinity, a normalized Laplacian, an eigendecomposition and a k-means - sixty
lines - and a dependency for sixty lines is a version axis nobody declared, on the arm whose whole
claim is that its structure is comparable to the engine's. The same reasoning the BM25 arm gives
for not importing a BM25. What is lost is sklearn's k-means++ implementation details; what is
gained is that this file's output depends on numpy's arithmetic and a declared seed, and on
nothing else.

THE SAMPLE CAP, which is the honest compromise and is declared rather than buried. A spectral
split needs an ``n x n`` affinity, and the bench view has 68,502 leaf spans - a 4.7-billion-entry
matrix that does not exist on any machine here. So a split of a large cluster runs the sweep on a
SEEDED SAMPLE of at most ``SAMPLE_CAP`` members, and the members that were not sampled are then
assigned to the nearest resulting centroid by cosine. That is the standard out-of-sample extension
of a spectral clustering, it keeps the method family intact (silhouette-chosen K over a spectral
split of a cosine affinity), and it is the reason the version axis says ``at-budget``: this is
RAPTOR's shape computed within a compute budget, not RAPTOR's shape computed exactly.

DETERMINISM. Every random choice - the sample, the k-means++ seeding - comes from a
``numpy.random.default_rng(seed)`` created per call from the declared seed, and ties break on
index. Two runs at one seed produce identical labels; a test asserts it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: The engine's branch clamp, kept: silhouette chooses K in ``[2, min(BRANCH_MAX, n-1)]``.
BRANCH_MAX = 8

#: The largest affinity a split will materialize. 1,000 x 1,000 is an 8 MB float64 matrix and a
#: sub-second ``eigh``; the whole tree is ~50 splits, so the fold's clustering cost stays minutes.
SAMPLE_CAP = 1000

#: k-means settings for the spectral embedding. Lloyd from a k-means++ start, seeded.
KMEANS_ITERS = 100
KMEANS_RESTARTS = 3


@dataclass(frozen=True)
class Split:
    """One split's outcome: the chosen K, a label per member, and the silhouette that chose it.

    ``unconstrained_k`` records what the sweep would have chosen over the FULL ``[2, branch_max]``
    range, whatever band the caller actually restricted it to. It exists so that a caller which
    narrows the band for a budget reason (RAPTOR does) can report the size of the compromise as a
    measured number instead of describing it.
    """

    k: int
    labels: np.ndarray
    silhouette: float
    sampled: int
    total: int
    unconstrained_k: int = 0
    unconstrained_silhouette: float = 0.0


def _unit(X: np.ndarray) -> np.ndarray:
    """L2-normalize rows. The vectors arrive unit already; this makes the guarantee local."""
    norms = np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    return X / norms


def _kmeans(Y: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    """Lloyd's algorithm from a k-means++ start, best of ``KMEANS_RESTARTS`` by inertia.

    Restarts are what stop a single unlucky seeding from deciding the tree's shape; taking the
    best by inertia (rather than the first) makes the result a property of the geometry and the
    seed together, which is what a declared seed is supposed to buy.
    """
    n = len(Y)
    best_labels, best_inertia = None, np.inf
    for _ in range(KMEANS_RESTARTS):
        # k-means++ seeding
        centers = [Y[rng.integers(n)]]
        for _ in range(1, k):
            d2 = np.min(
                np.stack([np.sum((Y - c) ** 2, axis=1) for c in centers]), axis=0)
            total = float(d2.sum())
            if total <= 0:
                centers.append(Y[rng.integers(n)])
                continue
            centers.append(Y[int(rng.choice(n, p=d2 / total))])
        C = np.asarray(centers, dtype=np.float64)
        labels = np.zeros(n, dtype=np.int64)
        for _ in range(KMEANS_ITERS):
            # Ties break on the LOWEST centroid index (argmin's own rule), so the assignment is
            # a function of the numbers and not of iteration order.
            d = ((Y[:, None, :] - C[None, :, :]) ** 2).sum(axis=2)
            new = np.argmin(d, axis=1)
            if np.array_equal(new, labels):
                break
            labels = new
            for j in range(k):
                members = Y[labels == j]
                if len(members):
                    C[j] = members.mean(axis=0)
        d = ((Y[:, None, :] - C[None, :, :]) ** 2).sum(axis=2)
        inertia = float(d[np.arange(n), labels].sum())
        if inertia < best_inertia:
            best_inertia, best_labels = inertia, labels
    return best_labels if best_labels is not None else np.zeros(n, dtype=np.int64)


def _spectral_embedding(A: np.ndarray, k_max: int) -> np.ndarray:
    """Top ``k_max`` eigenvectors of the symmetric normalized Laplacian, rows L2-normalized.

    Computed ONCE per split and sliced per K, rather than once per K: the eigenvectors of the
    normalized affinity do not depend on how many of them a given K will use.
    """
    deg = np.clip(A.sum(axis=1), 1e-12, None)
    dinv = 1.0 / np.sqrt(deg)
    L = A * dinv[:, None] * dinv[None, :]
    # ``eigh`` on a symmetric matrix returns ascending eigenvalues; the largest are the last.
    _vals, vecs = np.linalg.eigh(L)
    U = vecs[:, -k_max:][:, ::-1]
    return _unit(U)


def _silhouette(dist: np.ndarray, labels: np.ndarray) -> float:
    """Mean silhouette over a PRECOMPUTED distance matrix. Singleton clusters score 0, as usual."""
    n = len(labels)
    uniq = np.unique(labels)
    if len(uniq) < 2:
        return -1.0
    scores = np.zeros(n, dtype=np.float64)
    for j in uniq:
        mask = labels == j
        size = int(mask.sum())
        if size <= 1:
            scores[mask] = 0.0
            continue
        # a(i): mean distance to the OTHER members of i's own cluster (size-1 in the denominator).
        a = dist[np.ix_(mask, mask)].sum(axis=1) / (size - 1)
        b = np.full(size, np.inf)
        for other in uniq:
            if other == j:
                continue
            omask = labels == other
            if not omask.any():
                continue
            b = np.minimum(b, dist[np.ix_(mask, omask)].mean(axis=1))
        # A point identical to everything around it has a == b == 0 and no silhouette to speak
        # of; the convention is 0, and dividing to find that out raises a warning and yields NaN,
        # which then poisons the mean and silently decides K. Handled, not suppressed.
        denom = np.maximum(a, b)
        scores[mask] = np.where(denom > 0, (b - a) / np.where(denom > 0, denom, 1.0), 0.0)
    return float(scores.mean())


def best_split(X: np.ndarray, seed: int, branch_max: int = BRANCH_MAX,
               sample_cap: int = SAMPLE_CAP, branch_min: int = 2) -> Split:
    """Silhouette-chosen-K spectral split of ``X`` (unit rows). Returns a label per ROW of X.

    ``branch_min`` narrows the K sweep without changing how K is chosen inside it: the silhouette
    still picks, it just picks within a band. The full-range winner is computed anyway and
    returned as ``unconstrained_k``, so a caller that narrows the band has to report what it
    overrode rather than merely assert that the override was small.

    Large inputs are split on a seeded sample and the remainder is assigned to the nearest
    centroid by cosine - see the module docstring for why, and for what it costs.
    """
    n = len(X)
    if n < 4:
        return Split(k=1, labels=np.zeros(n, dtype=np.int64), silhouette=-1.0,
                     sampled=n, total=n)
    rng = np.random.default_rng(seed)
    if n > sample_cap:
        # Sorted so the sample is a set, not an order - the labels below are indexed by position.
        idx = np.sort(rng.choice(n, size=sample_cap, replace=False))
    else:
        idx = np.arange(n)
    S = _unit(np.asarray(X[idx], dtype=np.float64))

    gram = S @ S.T
    A = (gram + 1.0) / 2.0
    np.fill_diagonal(A, 1.0)
    dist = np.clip(1.0 - gram, 0.0, 2.0)
    np.fill_diagonal(dist, 0.0)

    hi = int(min(branch_max, len(S) - 1))
    if hi < 2:
        return Split(k=1, labels=np.zeros(n, dtype=np.int64), silhouette=-1.0,
                     sampled=len(S), total=n)
    U = _spectral_embedding(A, hi)

    lo = max(2, min(branch_min, hi))
    best_k, best_labels, best_s = lo, None, -2.0
    free_k, free_s = 2, -2.0
    for k in range(2, hi + 1):
        labels = _kmeans(U[:, :k], k, np.random.default_rng(seed + k))
        if len(np.unique(labels)) < 2:
            continue
        s = _silhouette(dist, labels)
        if s > free_s:
            free_k, free_s = k, s
        if k >= lo and s > best_s:
            best_k, best_labels, best_s = k, labels, s
    if best_labels is None:
        best_k = lo
        best_labels = _kmeans(U[:, :lo], lo, np.random.default_rng(seed + lo))
        best_s = _silhouette(dist, best_labels)

    if len(idx) == n:
        return Split(k=best_k, labels=best_labels.astype(np.int64), silhouette=best_s,
                     sampled=len(S), total=n, unconstrained_k=free_k,
                     unconstrained_silhouette=free_s)

    # Out-of-sample extension: centroid per label in the ORIGINAL space, nearest by cosine.
    centroids = np.stack([
        _unit(np.asarray(X[idx][best_labels == j], dtype=np.float64).mean(axis=0,
                                                                         keepdims=True))[0]
        if (best_labels == j).any() else np.zeros(X.shape[1])
        for j in range(best_k)
    ])
    sims = np.asarray(X, dtype=np.float64) @ centroids.T
    labels = np.argmax(sims, axis=1).astype(np.int64)
    labels[idx] = best_labels          # sampled members keep the label the split actually gave
    return Split(k=best_k, labels=labels, silhouette=best_s, sampled=len(S), total=n,
                 unconstrained_k=free_k, unconstrained_silhouette=free_s)
